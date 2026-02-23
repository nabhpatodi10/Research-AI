import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud.firestore import FieldFilter
from uuid_utils import uuid7

from research_progress import progress_message_for_node


class DatabaseJobsMixin:
    async def enqueue_pdf_processing_job(
        self,
        session_id: str,
        source_url: str,
        title: str,
        reason: str,
        partial_text_available: bool,
    ) -> str:
        return await asyncio.to_thread(
            self._enqueue_pdf_processing_job_sync,
            session_id,
            source_url,
            title,
            reason,
            partial_text_available,
        )

    def _enqueue_pdf_processing_job_sync(
        self,
        session_id: str,
        source_url: str,
        title: str,
        reason: str,
        partial_text_available: bool,
    ) -> str:
        now = datetime.now(timezone.utc)
        job_id = str(uuid7())
        payload = {
            "sessionId": session_id,
            "sourceUrl": source_url,
            "title": str(title or source_url),
            "status": "queued",
            "attempts": 0,
            "reason": str(reason or "primary_timeout"),
            "partialTextAvailable": bool(partial_text_available),
            "createdAt": now,
            "updatedAt": now,
            "nextRunAt": now,
            "lastError": None,
            "workerId": None,
        }
        self._firestore_client.collection("pdf_processing_jobs").document(job_id).set(payload)
        return job_id

    async def enqueue_research_job(
        self,
        user_id: str,
        session_id: str,
        research_idea: str,
        model_tier: str,
        research_breadth: str,
        research_depth: str,
        document_length: str,
    ) -> str:
        return await asyncio.to_thread(
            self._enqueue_research_job_sync,
            user_id,
            session_id,
            research_idea,
            model_tier,
            research_breadth,
            research_depth,
            document_length,
        )

    def _enqueue_research_job_sync(
        self,
        user_id: str,
        session_id: str,
        research_idea: str,
        model_tier: str,
        research_breadth: str,
        research_depth: str,
        document_length: str,
    ) -> str:
        now = datetime.now(timezone.utc)
        job_id = str(uuid7())
        normalized_idea = str(research_idea or "").strip()
        payload = {
            "userId": str(user_id),
            "sessionId": str(session_id),
            "status": "queued",
            "currentNode": "queued",
            "progressMessage": progress_message_for_node("queued"),
            "resumeFromNode": "generate_document_outline",
            "attempts": 0,
            "workerId": None,
            "error": None,
            "resultText": None,
            "createdAt": now,
            "updatedAt": now,
            "nextRunAt": now,
            "graphState": {
                "research_idea": normalized_idea,
            },
            "request": {
                "researchIdea": normalized_idea,
                "model": str(model_tier or "pro"),
                "researchBreadth": str(research_breadth or "medium"),
                "researchDepth": str(research_depth or "high"),
                "documentLength": str(document_length or "high"),
            },
        }
        self._firestore_client.collection("research_jobs").document(job_id).set(payload)
        return job_id

    async def claim_research_jobs(
        self,
        worker_id: str,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._claim_research_jobs_sync,
            worker_id,
            limit,
        )

    def _claim_research_jobs_sync(
        self,
        worker_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        now = datetime.now(timezone.utc)
        pending_query = (
            self._firestore_client.collection("research_jobs")
            .where(filter=FieldFilter("status", "==", "queued"))
            .limit(max(limit * 3, limit))
        )

        claimed: list[dict[str, Any]] = []
        for doc in pending_query.stream():
            data = doc.to_dict() or {}
            next_run = self._as_datetime(data.get("nextRunAt")) or now
            if next_run > now:
                continue

            try:
                started_at = data.get("startedAt") or now
                doc.reference.update(
                    {
                        "status": "running",
                        "currentNode": str(data.get("currentNode") or "preparing"),
                        "progressMessage": str(
                            data.get("progressMessage") or progress_message_for_node("preparing")
                        ),
                        "workerId": worker_id,
                        "updatedAt": now,
                        "startedAt": started_at,
                    }
                )
            except Exception:
                continue

            data["id"] = doc.id
            data["status"] = "running"
            data["currentNode"] = str(data.get("currentNode") or "preparing")
            data["progressMessage"] = str(
                data.get("progressMessage") or progress_message_for_node("preparing")
            )
            data["workerId"] = worker_id
            data["startedAt"] = started_at
            data["updatedAt"] = now
            claimed.append(data)
            if len(claimed) >= limit:
                break

        return claimed

    async def update_research_job_progress(
        self,
        job_id: str,
        current_node: str,
        progress_message: str,
        status: str = "running",
    ) -> None:
        await asyncio.to_thread(
            self._update_research_job_progress_sync,
            job_id,
            current_node,
            progress_message,
            status,
        )

    def _update_research_job_progress_sync(
        self,
        job_id: str,
        current_node: str,
        progress_message: str,
        status: str = "running",
    ) -> None:
        next_status = str(status or "running").strip().lower()
        if next_status not in {"queued", "running", "completed", "failed"}:
            next_status = "running"

        now = datetime.now(timezone.utc)
        self._firestore_client.collection("research_jobs").document(job_id).update(
            {
                "status": next_status,
                "currentNode": str(current_node or "").strip() or None,
                "progressMessage": str(progress_message or "").strip() or None,
                "updatedAt": now,
            }
        )

    async def update_research_job_checkpoint(
        self,
        job_id: str,
        graph_state: dict[str, Any],
        resume_from_node: str | None,
    ) -> None:
        await asyncio.to_thread(
            self._update_research_job_checkpoint_sync,
            job_id,
            graph_state,
            resume_from_node,
        )

    def _update_research_job_checkpoint_sync(
        self,
        job_id: str,
        graph_state: dict[str, Any],
        resume_from_node: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        normalized_resume = str(resume_from_node or "").strip() or None
        payload = {
            "graphState": graph_state if isinstance(graph_state, dict) else {},
            "resumeFromNode": normalized_resume,
            "updatedAt": now,
        }
        self._firestore_client.collection("research_jobs").document(job_id).update(payload)

    async def mark_research_job_completed(
        self,
        job_id: str,
        result_text: str,
    ) -> None:
        await asyncio.to_thread(self._mark_research_job_completed_sync, job_id, result_text)

    def _mark_research_job_completed_sync(
        self,
        job_id: str,
        result_text: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._firestore_client.collection("research_jobs").document(job_id).update(
            {
                "status": "completed",
                "currentNode": "completed",
                "progressMessage": progress_message_for_node("completed"),
                "resumeFromNode": None,
                "updatedAt": now,
                "completedAt": now,
                "workerId": None,
                "error": None,
                "resultText": str(result_text or ""),
            }
        )

    async def mark_research_job_failed(
        self,
        job_id: str,
        error_message: str,
        attempts: int,
        resume_from_node: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_research_job_failed_sync,
            job_id,
            error_message,
            attempts,
            resume_from_node,
        )

    def _mark_research_job_failed_sync(
        self,
        job_id: str,
        error_message: str,
        attempts: int,
        resume_from_node: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        normalized_resume = str(resume_from_node or "").strip() or None
        self._firestore_client.collection("research_jobs").document(job_id).update(
            {
                "status": "failed",
                "currentNode": "failed",
                "progressMessage": progress_message_for_node("failed"),
                "updatedAt": now,
                "failedAt": now,
                "workerId": None,
                "attempts": int(max(attempts, 0)),
                "error": str(error_message or "Research processing failed."),
                "resumeFromNode": normalized_resume,
            }
        )

    async def requeue_research_job(
        self,
        job_id: str,
        attempts: int,
        error_message: str,
        delay_seconds: float,
        resume_from_node: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._requeue_research_job_sync,
            job_id,
            attempts,
            error_message,
            delay_seconds,
            resume_from_node,
        )

    def _requeue_research_job_sync(
        self,
        job_id: str,
        attempts: int,
        error_message: str,
        delay_seconds: float,
        resume_from_node: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        next_run = now + timedelta(seconds=max(float(delay_seconds or 0.0), 0.0))
        normalized_resume = str(resume_from_node or "").strip() or None
        self._firestore_client.collection("research_jobs").document(job_id).update(
            {
                "status": "queued",
                "currentNode": "queued",
                "progressMessage": progress_message_for_node("queued"),
                "resumeFromNode": normalized_resume,
                "updatedAt": now,
                "nextRunAt": next_run,
                "workerId": None,
                "attempts": int(max(attempts, 0)),
                "error": str(error_message or "Research processing failed."),
            }
        )

    async def get_research_job(self, job_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_research_job_sync, job_id)

    def _get_research_job_sync(self, job_id: str) -> dict[str, Any] | None:
        snapshot = self._firestore_client.collection("research_jobs").document(job_id).get()
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        return self._serialize_research_job(snapshot.id, payload)

    async def get_active_research_job_for_session(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_active_research_job_for_session_sync, session_id)

    def _get_active_research_job_for_session_sync(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return None

        query = self._firestore_client.collection("research_jobs").where(
            filter=FieldFilter("sessionId", "==", normalized_session_id)
        )

        best_job: dict[str, Any] | None = None
        best_rank: tuple[int, datetime] | None = None
        for document in query.stream():
            payload = document.to_dict() or {}
            status = str(payload.get("status") or "").strip().lower()
            if status not in {"queued", "running"}:
                continue

            # Prefer running jobs over queued jobs, then most recently updated.
            status_priority = 2 if status == "running" else 1
            updated_at = self._as_datetime(payload.get("updatedAt"))
            if updated_at is None:
                updated_at = self._as_datetime(payload.get("createdAt")) or datetime.fromtimestamp(
                    0, tz=timezone.utc
                )
            rank = (status_priority, updated_at)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_job = self._serialize_research_job(document.id, payload)

        return best_job

    async def get_research_job_for_user(
        self,
        job_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_research_job_for_user_sync, job_id, user_id)

    def _get_research_job_for_user_sync(
        self,
        job_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        snapshot = self._firestore_client.collection("research_jobs").document(job_id).get()
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        if str(payload.get("userId") or "") != str(user_id):
            return None
        return self._serialize_research_job(snapshot.id, payload)

    async def claim_pdf_processing_jobs(
        self,
        worker_id: str,
        limit: int = 2,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._claim_pdf_processing_jobs_sync,
            worker_id,
            limit,
        )

    def _claim_pdf_processing_jobs_sync(
        self,
        worker_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        now = datetime.now(timezone.utc)
        pending_query = (
            self._firestore_client.collection("pdf_processing_jobs")
            .where(filter=FieldFilter("status", "==", "queued"))
            .limit(max(limit * 3, limit))
        )

        claimed: list[dict[str, Any]] = []
        for doc in pending_query.stream():
            data = doc.to_dict() or {}
            next_run = self._as_datetime(data.get("nextRunAt")) or now
            if next_run > now:
                continue

            try:
                doc.reference.update(
                    {
                        "status": "running",
                        "workerId": worker_id,
                        "updatedAt": now,
                        "startedAt": now,
                    }
                )
            except Exception:
                continue

            data["id"] = doc.id
            claimed.append(data)
            if len(claimed) >= limit:
                break

        return claimed

    async def mark_pdf_processing_job_completed(
        self,
        job_id: str,
        characters: int,
        page_count: int,
    ) -> None:
        await asyncio.to_thread(
            self._mark_pdf_processing_job_completed_sync,
            job_id,
            characters,
            page_count,
        )

    def _mark_pdf_processing_job_completed_sync(
        self,
        job_id: str,
        characters: int,
        page_count: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._firestore_client.collection("pdf_processing_jobs").document(job_id).update(
            {
                "status": "completed",
                "updatedAt": now,
                "completedAt": now,
                "resultCharacters": int(max(characters, 0)),
                "resultPageCount": int(max(page_count, 0)),
                "lastError": None,
            }
        )

    async def mark_pdf_processing_job_failed(
        self,
        job_id: str,
        error_message: str,
        attempts: int,
    ) -> None:
        await asyncio.to_thread(
            self._mark_pdf_processing_job_failed_sync,
            job_id,
            error_message,
            attempts,
        )

    def _mark_pdf_processing_job_failed_sync(
        self,
        job_id: str,
        error_message: str,
        attempts: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._firestore_client.collection("pdf_processing_jobs").document(job_id).update(
            {
                "status": "failed",
                "updatedAt": now,
                "failedAt": now,
                "attempts": int(max(attempts, 0)),
                "lastError": str(error_message or "Unknown PDF processing error."),
            }
        )

    async def requeue_pdf_processing_job(
        self,
        job_id: str,
        attempts: int,
        error_message: str,
        delay_seconds: float,
    ) -> None:
        await asyncio.to_thread(
            self._requeue_pdf_processing_job_sync,
            job_id,
            attempts,
            error_message,
            delay_seconds,
        )

    def _requeue_pdf_processing_job_sync(
        self,
        job_id: str,
        attempts: int,
        error_message: str,
        delay_seconds: float,
    ) -> None:
        now = datetime.now(timezone.utc)
        delay = max(float(delay_seconds or 0.0), 0.0)
        next_run = now + timedelta(seconds=delay)
        self._firestore_client.collection("pdf_processing_jobs").document(job_id).update(
            {
                "status": "queued",
                "updatedAt": now,
                "attempts": int(max(attempts, 0)),
                "nextRunAt": next_run,
                "lastError": str(error_message or "Unknown PDF processing error."),
                "workerId": None,
            }
        )

    @classmethod
    def _serialize_research_job(cls, job_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        request = raw.get("request") if isinstance(raw.get("request"), dict) else {}
        return {
            "id": str(job_id),
            "userId": str(raw.get("userId") or ""),
            "sessionId": str(raw.get("sessionId") or ""),
            "status": str(raw.get("status") or "queued"),
            "currentNode": (str(raw.get("currentNode")) if raw.get("currentNode") is not None else None),
            "progressMessage": (
                str(raw.get("progressMessage")) if raw.get("progressMessage") is not None else None
            ),
            "resumeFromNode": (
                str(raw.get("resumeFromNode")) if raw.get("resumeFromNode") is not None else None
            ),
            "attempts": int(raw.get("attempts") or 0),
            "error": (str(raw.get("error")) if raw.get("error") is not None else None),
            "resultText": str(raw.get("resultText") or ""),
            "workerId": (str(raw.get("workerId")) if raw.get("workerId") is not None else None),
            "createdAt": cls._datetime_iso(raw.get("createdAt")),
            "updatedAt": cls._datetime_iso(raw.get("updatedAt")),
            "startedAt": cls._datetime_iso_optional(raw.get("startedAt")),
            "completedAt": cls._datetime_iso_optional(raw.get("completedAt")),
            "failedAt": cls._datetime_iso_optional(raw.get("failedAt")),
            "request": {
                "researchIdea": str(request.get("researchIdea") or ""),
                "model": str(request.get("model") or "pro"),
                "researchBreadth": str(request.get("researchBreadth") or "medium"),
                "researchDepth": str(request.get("researchDepth") or "high"),
                "documentLength": str(request.get("documentLength") or "high"),
            },
            "graphState": raw.get("graphState") if isinstance(raw.get("graphState"), dict) else {},
        }
