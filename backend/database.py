from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore as firestore_module
from google.cloud.firestore import Client, FieldFilter
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_google_firestore import FirestoreChatMessageHistory, FirestoreVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from uuid_utils import uuid7

class Database:
    def __init__(self):
        project_id = os.getenv("GOOGLE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id and not os.getenv("GOOGLE_CLOUD_PROJECT"):
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id

        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path and not os.path.isabs(credentials_path):
            resolved_credentials_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), credentials_path)
            )
            if os.path.exists(resolved_credentials_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = resolved_credentials_path

        self.__firestore_client = Client(project=project_id)
        self.__embeddingModel = GoogleGenerativeAIEmbeddings(
            model="text-embedding-005",
            vertexai=True,
            project=project_id,
            location=os.getenv("GOOGLE_CLOUD_LOCATION"),
        )
        self.__splitter = RecursiveCharacterTextSplitter(chunk_size=6500, chunk_overlap=200)

    async def chat(self, session_id: str) -> FirestoreChatMessageHistory:
        return FirestoreChatMessageHistory(
            session_id=session_id,
            collection="chats",
            client=self.__firestore_client,
            encode_message=False,
        )

    async def vector_store(self) -> FirestoreVectorStore:
        vectorStore = FirestoreVectorStore(
            collection="vector",
            embedding_service=self.__embeddingModel,
            client=self.__firestore_client,
        )
        return vectorStore

    def _clear_vector_store_sync(self, session_id: str, batch_size: int = 5000) -> int | None:
        collection_ref = self.__firestore_client.collection("vector")
        session_filter = FieldFilter("metadata.session_id", "==", session_id)

        deleted = 0

        while True:
            docs = list(collection_ref.where(filter=session_filter).limit(batch_size).stream())
            if not docs:
                break
            batch = self.__firestore_client.batch()
            for doc in docs:
                batch.delete(doc.reference)
                deleted += 1
            batch.commit()

        return deleted

    async def clear_vector_store(self, session_id: str, batch_size: int = 5000) -> int | None:
        return await asyncio.to_thread(self._clear_vector_store_sync, session_id, batch_size)

    async def add_data(self, session_id: str, documents: list[Document]) -> None:
        if not documents:
            print(f"No documents to add for session {session_id}.")
            return

        vector_store = await self.vector_store()
        split_docs = self.__splitter.split_documents(documents)
        if not split_docs:
            print(f"Splitter returned no chunks for session {session_id}.")
            return

        for split_doc in split_docs:
            metadata = dict(split_doc.metadata or {})
            metadata["session_id"] = session_id
            split_doc.metadata = metadata

        ids = [str(uuid7()) for _ in range(len(split_docs))]
        try:
            added = await vector_store.aadd_documents(split_docs, ids=ids)
            if isinstance(added, list) and len(added) == 0:
                print(f"Vector store add returned no ids for session {session_id}.")
            else:
                added_count = len(added) if isinstance(added, list) else len(split_docs)
                print(f"Added {added_count}/{len(split_docs)} vector chunks for session {session_id}.")
            return
        except Exception as bulk_error:
            added_count = 0
            for doc, doc_id in zip(split_docs, ids):
                try:
                    await vector_store.aadd_documents([doc], ids=[doc_id])
                    added_count += 1
                except Exception:
                    continue

            if added_count == 0:
                raise bulk_error

            print(
                f"Partially added {added_count}/{len(split_docs)} vector chunks for session {session_id}."
            )

    @staticmethod
    def _normalize_vector_metadata(metadata: Any) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        if not isinstance(metadata, dict):
            return normalized

        nested_metadata = metadata.get("metadata")
        if isinstance(nested_metadata, dict):
            normalized.update(nested_metadata)

        for field_name in ("source", "title", "session_id"):
            field_value = metadata.get(field_name)
            if field_value is not None:
                normalized[field_name] = field_value

        reference = metadata.get("reference")
        if isinstance(reference, dict):
            reference_path = reference.get("path")
            if isinstance(reference_path, str) and reference_path.strip():
                normalized["reference_path"] = reference_path

        if not normalized:
            return dict(metadata)
        return normalized

    @staticmethod
    def _extract_vector_page_content(
        page_content: Any,
        metadata: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(page_content, str):
            stripped = page_content.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    return page_content, metadata

                if isinstance(payload, dict):
                    payload_metadata = payload.get("metadata")
                    if isinstance(payload_metadata, dict):
                        merged_metadata = dict(payload_metadata)
                        merged_metadata.update(metadata)
                        metadata = merged_metadata

                    payload_content = payload.get("content")
                    if isinstance(payload_content, str):
                        return payload_content, metadata

            return page_content, metadata

        return str(page_content or ""), metadata

    def _normalize_vector_documents(
        self,
        session_id: str,
        documents: list[Document],
    ) -> list[Document]:
        normalized_documents: list[Document] = []
        for document in documents:
            metadata = self._normalize_vector_metadata(getattr(document, "metadata", {}))
            page_content, metadata = self._extract_vector_page_content(
                getattr(document, "page_content", ""),
                metadata,
            )

            cleaned_content = str(page_content or "").strip()
            if not cleaned_content:
                continue

            if not metadata.get("session_id"):
                metadata["session_id"] = session_id

            normalized_documents.append(
                Document(page_content=cleaned_content, metadata=metadata)
            )

        return normalized_documents

    async def vector_search(self, session_id: str, query: str) -> list[Document]:
        try:
            vector_store = await self.vector_store()
            session_filter = FieldFilter("metadata.session_id", "==", session_id)
            documents = await vector_store.amax_marginal_relevance_search(
                query=query,
                k=5,
                fetch_k=50,
                filters=session_filter,
            )
            return self._normalize_vector_documents(session_id=session_id, documents=documents)
        except Exception as error:
            raise error

    async def add_messages(self, session_id: str, message: BaseMessage | list[BaseMessage]) -> None:
        try:
            chat = await self.chat(session_id=session_id)
            if isinstance(message, list):
                return await chat.aadd_messages(message)
            return await chat.aadd_messages([message])
        except Exception as error:
            raise error

    async def get_messages(self, session_id: str) -> list[BaseMessage]:
        try:
            chat = await self.chat(session_id=session_id)
            return await chat.aget_messages()
        except Exception as error:
            raise error

    async def clear_chat(self, session_id: str) -> None:
        try:
            chat = await self.chat(session_id=session_id)
            await chat.aclear()
            await self.clear_vector_store(session_id=session_id)
        except Exception as error:
            raise error

    @staticmethod
    def _as_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if hasattr(value, "to_datetime"):
            converted = value.to_datetime()
            if isinstance(converted, datetime):
                if converted.tzinfo is None:
                    return converted.replace(tzinfo=timezone.utc)
                return converted
        return None

    @classmethod
    def _datetime_iso(cls, value: Any) -> str:
        dt = cls._as_datetime(value) or datetime.now(timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    @classmethod
    def _serialize_session(cls, session_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": session_id,
            "topic": str(raw.get("topic") or "Untitled Session"),
            "createdAt": cls._datetime_iso(raw.get("createdAt")),
            "isShared": bool(raw.get("isShared", False)),
            "sharedBy": raw.get("sharedBy"),
        }

    def _get_user_chats_sessions_sync(self, user_id: str) -> dict[str, dict[str, Any]]:
        doc_ref = self.__firestore_client.collection("user_chats").document(user_id)
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
        user_ref = self.__firestore_client.collection("users").document(user_id)
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
        query = self.__firestore_client.collection("users").where("email", "==", email).limit(1)
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
        snapshot = self.__firestore_client.collection("users").document(user_id).get()
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
        doc_ref = self.__firestore_client.collection("user_chats").document(user_id)
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
            "pendingResearch": bool(existing.get("pendingResearch", False)),
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
        self.__firestore_client.collection("user_chats").document(user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )

    async def touch_user_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._touch_user_session_sync, user_id, session_id)

    def _touch_user_session_sync(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        sessions = self._get_user_chats_sessions_sync(user_id)
        existing = sessions.get(session_id)
        if existing is None:
            return None

        payload = dict(existing)
        payload["createdAt"] = datetime.now(timezone.utc)
        self.__firestore_client.collection("user_chats").document(user_id).set(
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
        self.__firestore_client.collection("user_chats").document(user_id).set(
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
        self.__firestore_client.collection("user_chats").document(user_id).update(
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
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._share_session_to_user_sync,
            from_user_id,
            to_user_id,
            session_id,
            topic,
            shared_by_email,
        )

    def _share_session_to_user_sync(
        self,
        from_user_id: str,
        to_user_id: str,
        session_id: str,
        topic: str,
        shared_by_email: str,
    ) -> dict[str, Any]:
        payload = {
            "topic": str(topic or "").strip() or "Untitled Session",
            "createdAt": datetime.now(timezone.utc),
            "isShared": True,
            "sharedBy": shared_by_email,
            "originalOwnerId": from_user_id,
            "pendingResearch": False,
        }
        self.__firestore_client.collection("user_chats").document(to_user_id).set(
            {"sessions": {session_id: payload}},
            merge=True,
        )
        return self._serialize_session(session_id, payload)

    async def user_has_session(self, user_id: str, session_id: str) -> bool:
        return await asyncio.to_thread(self._user_has_session_sync, user_id, session_id)

    def _user_has_session_sync(self, user_id: str, session_id: str) -> bool:
        sessions = self._get_user_chats_sessions_sync(user_id)
        return session_id in sessions

    @classmethod
    def _message_text(cls, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") == "text" and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif isinstance(item.get("content"), str):
                        parts.append(item["content"])
            return "\n".join(part for part in parts if part.strip())
        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                return content["text"]
            if isinstance(content.get("content"), str):
                return content["content"]
            return str(content)
        return str(content or "")

    async def get_session_messages_for_ui(self, session_id: str) -> list[dict[str, str]]:
        messages = await self.get_messages(session_id)
        ui_messages: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            sender = None
            if isinstance(message, HumanMessage):
                sender = "user"
            elif isinstance(message, AIMessage):
                sender = "ai"
            if sender is None:
                continue

            text = self._message_text(getattr(message, "content", "")).strip()
            if not text:
                continue

            ui_messages.append({"id": f"msg-{index}", "sender": sender, "text": text})
        return ui_messages

    async def add_feedback(
        self,
        user_id: str,
        user_email: str,
        feedback_type: str,
        satisfaction: str,
        comments: str,
    ) -> None:
        await asyncio.to_thread(
            self._add_feedback_sync,
            user_id,
            user_email,
            feedback_type,
            satisfaction,
            comments,
        )

    def _add_feedback_sync(
        self,
        user_id: str,
        user_email: str,
        feedback_type: str,
        satisfaction: str,
        comments: str,
    ) -> None:
        self.__firestore_client.collection("feedback").add(
            {
                "userId": user_id,
                "userEmail": user_email,
                "feedbackType": feedback_type,
                "satisfaction": satisfaction,
                "comments": comments,
                "createdAt": datetime.now(timezone.utc),
            }
        )

    def close_connection(self) -> None:
        self.__firestore_client.close()
