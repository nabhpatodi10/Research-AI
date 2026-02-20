import asyncio
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore as firestore_module


class DatabaseSessionsMixin:
    @staticmethod
    def _normalize_share_mode(raw_mode: Any, is_shared: bool) -> str | None:
        mode = str(raw_mode or "").strip().lower()
        if mode in {"collaborative", "snapshot"}:
            return mode
        if is_shared:
            return "collaborative"
        return None

    @staticmethod
    def _normalize_active_task(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        task_id = str(raw.get("id") or "").strip()
        task_type = str(raw.get("type") or "").strip().lower()
        status = str(raw.get("status") or "").strip().lower()
        if not task_id or task_type != "research" or status not in {"queued", "running"}:
            return None
        created_at = raw.get("createdAt") or datetime.now(timezone.utc)
        updated_at = raw.get("updatedAt") or created_at
        current_node = str(raw.get("current_node") or raw.get("currentNode") or "").strip() or None
        progress_message = (
            str(raw.get("progress_message") or raw.get("progressMessage") or "").strip() or None
        )
        return {
            "id": task_id,
            "type": "research",
            "status": status,
            "current_node": current_node,
            "progress_message": progress_message,
            "createdAt": created_at,
            "updatedAt": updated_at,
        }

    @classmethod
    def _serialize_active_task(cls, raw: Any) -> dict[str, Any] | None:
        normalized = cls._normalize_active_task(raw)
        if normalized is None:
            return None
        return {
            "id": normalized["id"],
            "type": normalized["type"],
            "status": normalized["status"],
            "current_node": normalized.get("current_node"),
            "progress_message": normalized.get("progress_message"),
            "createdAt": cls._datetime_iso(normalized.get("createdAt")),
            "updatedAt": cls._datetime_iso(normalized.get("updatedAt")),
        }

    @classmethod
    def _serialize_session(cls, session_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        is_shared = bool(raw.get("isShared", False))
        return {
            "id": session_id,
            "topic": str(raw.get("topic") or "Untitled Session"),
            "createdAt": cls._datetime_iso(raw.get("createdAt")),
            "isShared": is_shared,
            "sharedBy": raw.get("sharedBy"),
            "shareMode": cls._normalize_share_mode(raw.get("shareMode"), is_shared),
            "sourceSessionId": (
                str(raw.get("sourceSessionId") or "").strip() or None
            ),
        }

    def _get_user_chats_sessions_sync(self, user_id: str) -> dict[str, dict[str, Any]]:
        doc_ref = self._firestore_client.collection("user_chats").document(user_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return {}
        data = snapshot.to_dict() or {}
        sessions = data.get("sessions")
        if not isinstance(sessions, dict):
            return {}
        normalized: dict[str, dict[str, Any]] = {}
        for session_id, raw in sessions.items():
            if isinstance(raw, dict):
                normalized[str(session_id)] = raw
        return normalized

    async def upsert_user(
        self, user_id: str, email: str, name: str | None, provider: str
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._upsert_user_sync, user_id, email, name, provider)

    def _upsert_user_sync(
        self, user_id: str, email: str, name: str | None, provider: str
    ) -> dict[str, Any]:
        user_ref = self._firestore_client.collection("users").document(user_id)
        snapshot = user_ref.get()
        existing = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)
        preferred_name = str(name or "").strip()
        existing_name = str(existing.get("name") or "").strip()
        resolved_name = preferred_name or existing_name or email.split("@")[0]
        payload = {
            "uid": user_id,
            "email": email,
            "name": resolved_name,
            "provider": provider,
            "lastLogin": now,
        }
        if not snapshot.exists:
            payload["createdAt"] = now
        user_ref.set(payload, merge=True)
        return {
            "id": user_id,
            "email": payload["email"],
            "name": payload["name"],
            "provider": payload["provider"],
        }

    async def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._find_user_by_email_sync, email)

    def _find_user_by_email_sync(self, email: str) -> dict[str, Any] | None:
        query = self._firestore_client.collection("users").where("email", "==", email).limit(1)
        docs = list(query.stream())
        if not docs:
            return None
        doc = docs[0]
        payload = doc.to_dict() or {}
        return {
            "id": doc.id,
            "email": payload.get("email"),
            "name": payload.get("name"),
            "provider": payload.get("provider"),
        }

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_user_sync, user_id)

    def _get_user_sync(self, user_id: str) -> dict[str, Any] | None:
        snapshot = self._firestore_client.collection("users").document(user_id).get()
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        return {
            "id": snapshot.id,
            "email": payload.get("email"),
            "name": payload.get("name"),
            "provider": payload.get("provider"),
        }

    async def ensure_user_chat_session(
        self,
        user_id: str,
        session_id: str,
        topic: str,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._ensure_user_chat_session_sync, user_id, session_id, topic, created_at
        )

    def _ensure_user_chat_session_sync(
        self,
        user_id: str,
        session_id: str,
        topic: str,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        doc_ref = self._firestore_client.collection("user_chats").document(user_id)
        sessions = self._get_user_chats_sessions_sync(user_id)
        existing = sessions.get(session_id, {})
        existing_topic = str(existing.get("topic") or "").strip()
        resolved_topic = existing_topic or str(topic or "").strip() or "Untitled Session"
        resolved_created = existing.get("createdAt") or created_at or datetime.now(timezone.utc)
        payload = {
            "topic": resolved_topic,
            "createdAt": resolved_created,
            "isShared": bool(existing.get("isShared", False)),
            "sharedBy": existing.get("sharedBy"),
            "shareMode": self._normalize_share_mode(
                existing.get("shareMode"),
                bool(existing.get("isShared", False)),
            ),
            "sourceSessionId": (
                str(existing.get("sourceSessionId") or "").strip() or None
            ),
            "pendingResearch": bool(existing.get("pendingResearch", False)),
            "activeTask": existing.get("activeTask"),
        }
        if existing.get("originalOwnerId") is not None:
            payload["originalOwnerId"] = existing.get("originalOwnerId")
        doc_ref.set({"sessions": {session_id: payload}}, merge=True)
        return self._serialize_session(session_id, payload)

    async def list_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_user_sessions_sync, user_id)

    def _list_user_sessions_sync(self, user_id: str) -> list[dict[str, Any]]:
        sessions = self._get_user_chats_sessions_sync(user_id)
        enriched: list[tuple[datetime, dict[str, Any]]] = []
        for session_id, raw in sessions.items():
            dt = self._as_datetime(raw.get("createdAt")) or datetime.fromtimestamp(0, tz=timezone.utc)
            enriched.append((dt, self._serialize_session(session_id, raw)))
        enriched.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in enriched]

    async def get_user_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_user_session_sync, user_id, session_id)

    def _get_user_session_sync(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        sessions = self._get_user_chats_sessions_sync(user_id)
        raw = sessions.get(session_id)
        if raw is None:
            return None
        return self._serialize_session(session_id, raw)

    async def get_user_session_pending_research(self, user_id: str, session_id: str) -> bool:
        return await asyncio.to_thread(self._get_user_session_pending_research_sync, user_id, session_id)

    def _get_user_session_pending_research_sync(self, user_id: str, session_id: str) -> bool:
        sessions = self._get_user_chats_sessions_sync(user_id)
        raw = sessions.get(session_id)
        if not isinstance(raw, dict):
            return False
        return bool(raw.get("pendingResearch", False))

    async def set_user_session_pending_research(
        self,
        user_id: str,
        session_id: str,
        pending: bool,
    ) -> None:
        await asyncio.to_thread(self._set_user_session_pending_research_sync, user_id, session_id, pending)

    def _set_user_session_pending_research_sync(
        self,
        user_id: str,
        session_id: str,
        pending: bool,
    ) -> None:
        sessions = self._get_user_chats_sessions_sync(user_id)
        existing = sessions.get(session_id)
        if existing is None:
            return

        payload = dict(existing)
        payload["pendingResearch"] = bool(pending)
        payload["createdAt"] = payload.get("createdAt") or datetime.now(timezone.utc)
        self._firestore_client.collection("user_chats").document(user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )

    async def get_user_session_active_task(
        self,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_user_session_active_task_sync, user_id, session_id)

    def _get_user_session_active_task_sync(
        self,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        sessions = self._get_user_chats_sessions_sync(user_id)
        raw = sessions.get(session_id)
        if not isinstance(raw, dict):
            return None
        return self._serialize_active_task(raw.get("activeTask"))

    async def set_user_session_active_task(
        self,
        user_id: str,
        session_id: str,
        task: dict[str, Any] | None,
    ) -> None:
        await asyncio.to_thread(
            self._set_user_session_active_task_sync,
            user_id,
            session_id,
            task,
        )

    def _set_user_session_active_task_sync(
        self,
        user_id: str,
        session_id: str,
        task: dict[str, Any] | None,
    ) -> None:
        sessions = self._get_user_chats_sessions_sync(user_id)
        existing = sessions.get(session_id)
        if existing is None:
            return

        payload = dict(existing)
        now = datetime.now(timezone.utc)
        if task is None:
            payload["activeTask"] = None
        else:
            normalized = self._normalize_active_task(task)
            if normalized is None:
                return
            normalized["createdAt"] = self._as_datetime(normalized.get("createdAt")) or now
            normalized["updatedAt"] = now
            payload["activeTask"] = normalized

        payload["createdAt"] = payload.get("createdAt") or now
        self._firestore_client.collection("user_chats").document(user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )

    async def set_user_session_active_task_status(
        self,
        user_id: str,
        session_id: str,
        task_id: str,
        status: str,
    ) -> bool:
        return await asyncio.to_thread(
            self._set_user_session_active_task_status_sync,
            user_id,
            session_id,
            task_id,
            status,
        )

    def _set_user_session_active_task_status_sync(
        self,
        user_id: str,
        session_id: str,
        task_id: str,
        status: str,
    ) -> bool:
        next_status = str(status or "").strip().lower()
        if next_status not in {"queued", "running"}:
            return False

        sessions = self._get_user_chats_sessions_sync(user_id)
        existing = sessions.get(session_id)
        if existing is None:
            return False

        payload = dict(existing)
        active_task = self._normalize_active_task(payload.get("activeTask"))
        if active_task is None or active_task.get("id") != str(task_id):
            return False

        active_task["status"] = next_status
        active_task["updatedAt"] = datetime.now(timezone.utc)
        payload["activeTask"] = active_task
        payload["createdAt"] = payload.get("createdAt") or datetime.now(timezone.utc)
        self._firestore_client.collection("user_chats").document(user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )
        return True

    async def clear_user_session_active_task_if_matches(
        self,
        user_id: str,
        session_id: str,
        task_id: str,
    ) -> bool:
        return await asyncio.to_thread(
            self._clear_user_session_active_task_if_matches_sync,
            user_id,
            session_id,
            task_id,
        )

    def _clear_user_session_active_task_if_matches_sync(
        self,
        user_id: str,
        session_id: str,
        task_id: str,
    ) -> bool:
        sessions = self._get_user_chats_sessions_sync(user_id)
        existing = sessions.get(session_id)
        if existing is None:
            return False

        payload = dict(existing)
        active_task = self._normalize_active_task(payload.get("activeTask"))
        if active_task is None or active_task.get("id") != str(task_id):
            return False

        payload["activeTask"] = None
        payload["createdAt"] = payload.get("createdAt") or datetime.now(timezone.utc)
        self._firestore_client.collection("user_chats").document(user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )
        return True

    async def touch_user_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._touch_user_session_sync, user_id, session_id)

    def _touch_user_session_sync(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        sessions = self._get_user_chats_sessions_sync(user_id)
        existing = sessions.get(session_id)
        if existing is None:
            return None

        payload = dict(existing)
        payload["createdAt"] = datetime.now(timezone.utc)
        self._firestore_client.collection("user_chats").document(user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )
        return self._serialize_session(session_id, payload)

    async def rename_user_session(
        self, user_id: str, session_id: str, topic: str
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._rename_user_session_sync, user_id, session_id, topic)

    def _rename_user_session_sync(
        self, user_id: str, session_id: str, topic: str
    ) -> dict[str, Any] | None:
        sessions = self._get_user_chats_sessions_sync(user_id)
        existing = sessions.get(session_id)
        if existing is None:
            return None
        payload = dict(existing)
        payload["topic"] = str(topic or "").strip() or "Untitled Session"
        payload["createdAt"] = payload.get("createdAt") or datetime.now(timezone.utc)
        self._firestore_client.collection("user_chats").document(user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )
        return self._serialize_session(session_id, payload)

    async def delete_user_session(self, user_id: str, session_id: str) -> bool:
        return await asyncio.to_thread(self._delete_user_session_sync, user_id, session_id)

    def _delete_user_session_sync(self, user_id: str, session_id: str) -> bool:
        sessions = self._get_user_chats_sessions_sync(user_id)
        if session_id not in sessions:
            return False
        self._firestore_client.collection("user_chats").document(user_id).update(
            {f"sessions.{session_id}": firestore_module.DELETE_FIELD}
        )
        return True

    async def share_session_to_user(
        self,
        from_user_id: str,
        to_user_id: str,
        session_id: str,
        topic: str,
        shared_by_email: str,
        share_mode: str = "collaborative",
        source_session_id: str | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._share_session_to_user_sync,
            from_user_id,
            to_user_id,
            session_id,
            topic,
            shared_by_email,
            share_mode,
            source_session_id,
        )

    def _share_session_to_user_sync(
        self,
        from_user_id: str,
        to_user_id: str,
        session_id: str,
        topic: str,
        shared_by_email: str,
        share_mode: str = "collaborative",
        source_session_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_mode = self._normalize_share_mode(share_mode, True) or "collaborative"
        existing_sessions = self._get_user_chats_sessions_sync(to_user_id)
        existing = existing_sessions.get(session_id)
        if isinstance(existing, dict):
            if normalized_mode == "collaborative":
                return self._serialize_session(session_id, existing)
            raise ValueError(f"Session id already exists for recipient: {session_id}")

        payload = {
            "topic": str(topic or "").strip() or "Untitled Session",
            "createdAt": datetime.now(timezone.utc),
            "isShared": True,
            "sharedBy": shared_by_email,
            "shareMode": normalized_mode,
            "sourceSessionId": (str(source_session_id or "").strip() or None),
            "originalOwnerId": from_user_id,
            "pendingResearch": False,
            "activeTask": None,
        }
        self._firestore_client.collection("user_chats").document(to_user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )
        return self._serialize_session(session_id, payload)

    async def user_has_session(self, user_id: str, session_id: str) -> bool:
        return await asyncio.to_thread(self._user_has_session_sync, user_id, session_id)

    def _user_has_session_sync(self, user_id: str, session_id: str) -> bool:
        sessions = self._get_user_chats_sessions_sync(user_id)
        return session_id in sessions
