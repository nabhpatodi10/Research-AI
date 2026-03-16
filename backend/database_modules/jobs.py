import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google.api_core import exceptions as google_exceptions
from google.cloud.firestore import FieldFilter
from uuid_utils import uuid7

from research_progress import progress_message_for_node
from settings import get_settings


logger = logging.getLogger(__name__)


class DatabaseJobsMixin:
    _CLAIM_LOG_EVENT_STALE = "stale-warning"
    _CLAIM_LOG_EVENT_ERROR = "claim-error"
    _OWNED_JOB_WRITE_MAX_ATTEMPTS = 4

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
            "progressDetails": None,
            "resumeFromNode": "generate_document_outline",
            "attempts": 0,
            "workerId": None,
            "lastHeartbeatAt": None,
            "leaseExpiresAt": None,
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

    @staticmethod
    def _normalize_worker_id(worker_id: str | None) -> str | None:
        normalized = str(worker_id or "").strip()
        return normalized or None

    def _is_research_job_running_stale(
        self,
        payload: dict[str, Any],
        *,
        now: datetime,
        stale_timeout_seconds: float,
    ) -> bool:
        lease_expires_at = self._as_datetime(payload.get("leaseExpiresAt"))
        if lease_expires_at is not None:
            return lease_expires_at <= now

        updated_at = self._as_datetime(payload.get("updatedAt"))
        if updated_at is None:
            updated_at = self._as_datetime(payload.get("createdAt")) or now
        stale_seconds = max(float(stale_timeout_seconds or 0.0), 0.0)
        return (now - updated_at).total_seconds() >= stale_seconds

    def _heartbeat_age_seconds(
        self,
        payload: dict[str, Any],
        *,
        now: datetime,
    ) -> float:
        heartbeat_at = self._as_datetime(payload.get("lastHeartbeatAt"))
        if heartbeat_at is None:
            heartbeat_at = self._as_datetime(payload.get("updatedAt"))
        if heartbeat_at is None:
            heartbeat_at = self._as_datetime(payload.get("createdAt")) or now
        return max((now - heartbeat_at).total_seconds(), 0.0)

    @staticmethod
    def _is_firestore_write_race(error: Exception) -> bool:
        return isinstance(
            error,
            (
                google_exceptions.Aborted,
                google_exceptions.Conflict,
                google_exceptions.FailedPrecondition,
                google_exceptions.PreconditionFailed,
                google_exceptions.NotFound,
            ),
        )

    def _write_option_for_snapshot(self, snapshot: Any) -> Any:
        update_time = getattr(snapshot, "update_time", None)
        if update_time is not None:
            return self._firestore_client.write_option(last_update_time=update_time)
        return self._firestore_client.write_option(exists=True)

    def _update_snapshot_if_unchanged_sync(
        self,
        snapshot: Any,
        update_payload: dict[str, Any],
    ) -> bool:
        if not getattr(snapshot, "exists", False):
            return False
        try:
            snapshot.reference.update(
                update_payload,
                option=self._write_option_for_snapshot(snapshot),
            )
        except Exception as error:
            if self._is_firestore_write_race(error):
                return False
            raise
        return True

    def _owned_job_snapshot_matches(
        self,
        payload: dict[str, Any],
        *,
        expected_worker_id: str | None,
        allowed_statuses: set[str] | None,
    ) -> bool:
        normalized_worker_id = self._normalize_worker_id(expected_worker_id)
        if normalized_worker_id is not None:
            current_worker_id = self._normalize_worker_id(payload.get("workerId"))
            if current_worker_id != normalized_worker_id:
                return False

        if allowed_statuses is not None:
            current_status = str(payload.get("status") or "").strip().lower()
            if current_status not in allowed_statuses:
                return False

        return True

    def _job_claim_log_cache(self) -> dict[str, datetime]:
        cache = getattr(self, "_research_job_claim_log_cache", None)
        if isinstance(cache, dict):
            return cache
        cache = {}
        self._research_job_claim_log_cache = cache
        return cache

    def _should_log_claim_event(
        self,
        *,
        job_id: str,
        event: str,
        now: datetime,
        suppression_window_seconds: float,
    ) -> bool:
        window_seconds = max(float(suppression_window_seconds or 0.0), 0.0)
        if window_seconds <= 0:
            return True

        cache = self._job_claim_log_cache()
        key = f"{event}:{job_id}"
        previous = self._as_datetime(cache.get(key))
        if previous is not None and (now - previous).total_seconds() < window_seconds:
            return False
        cache[key] = now
        return True

    def _claim_research_job_document_sync(
        self,
        document,
        *,
        worker_id: str,
        now: datetime,
        lease_duration_seconds: float,
        stale_timeout_seconds: float,
    ) -> dict[str, Any] | None:
        normalized_worker_id = self._normalize_worker_id(worker_id)
        if normalized_worker_id is None:
            return None

        if not getattr(document, "exists", False):
            return None

        lease_expires_at = now + timedelta(seconds=max(float(lease_duration_seconds or 0.0), 1.0))
        payload = document.to_dict() or {}
        status = str(payload.get("status") or "").strip().lower()
        if status == "queued":
            next_run = self._as_datetime(payload.get("nextRunAt")) or now
            if next_run > now:
                return None
        elif status == "running":
            if not self._is_research_job_running_stale(
                payload,
                now=now,
                stale_timeout_seconds=stale_timeout_seconds,
            ):
                return None
        else:
            return None

        started_at = self._as_datetime(payload.get("startedAt")) or now
        current_node = str(payload.get("currentNode") or "preparing")
        progress_message = str(
            payload.get("progressMessage") or progress_message_for_node(current_node)
        )
        update_payload = {
            "status": "running",
            "currentNode": current_node,
            "progressMessage": progress_message,
            "workerId": normalized_worker_id,
            "updatedAt": now,
            "startedAt": started_at,
            "lastHeartbeatAt": now,
            "leaseExpiresAt": lease_expires_at,
        }
        if not self._update_snapshot_if_unchanged_sync(document, update_payload):
            return None

        payload.update(update_payload)
        payload["id"] = document.id
        return payload

    def _update_research_job_if_owned_sync(
        self,
        job_id: str,
        *,
        update_payload: dict[str, Any],
        expected_worker_id: str | None,
        allowed_statuses: set[str] | None = None,
    ) -> bool:
        document = self._firestore_client.collection("research_jobs").document(job_id)
        for _attempt in range(self._OWNED_JOB_WRITE_MAX_ATTEMPTS):
            snapshot = document.get()
            if not snapshot.exists:
                return False

            payload = snapshot.to_dict() or {}
            if not self._owned_job_snapshot_matches(
                payload,
                expected_worker_id=expected_worker_id,
                allowed_statuses=allowed_statuses,
            ):
                return False

            try:
                snapshot.reference.update(
                    update_payload,
                    option=self._write_option_for_snapshot(snapshot),
                )
                return True
            except Exception as error:
                if not self._is_firestore_write_race(error):
                    raise

        final_snapshot = document.get()
        if not final_snapshot.exists:
            return False

        final_payload = final_snapshot.to_dict() or {}
        if not self._owned_job_snapshot_matches(
            final_payload,
            expected_worker_id=expected_worker_id,
            allowed_statuses=allowed_statuses,
        ):
            return False

        raise RuntimeError(
            f"Repeated Firestore contention while updating owned research job {job_id}."
        )

    async def claim_research_jobs(
        self,
        worker_id: str,
        limit: int = 6,
        lease_duration_seconds: float = 180.0,
        stale_warning_seconds: float = 300.0,
        stale_timeout_seconds: float = 1200.0,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._claim_research_jobs_sync,
            worker_id,
            limit,
            lease_duration_seconds,
            stale_warning_seconds,
            stale_timeout_seconds,
        )

    def _claim_research_jobs_sync(
        self,
        worker_id: str,
        limit: int,
        lease_duration_seconds: float,
        stale_warning_seconds: float,
        stale_timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        now = datetime.now(timezone.utc)
        collection = self._firestore_client.collection("research_jobs")
        pending_query = (
            collection
            .where(filter=FieldFilter("status", "==", "running"))
            .limit(max(limit * 4, limit))
        )
        queued_query = (
            self._firestore_client.collection("research_jobs")
            .where(filter=FieldFilter("status", "==", "queued"))
            .limit(max(limit * 3, limit))
        )

        claimed: list[dict[str, Any]] = []
        warning_window_seconds = max(float(stale_warning_seconds or 0.0), 0.0)
        for doc in pending_query.stream():
            data = doc.to_dict() or {}
            heartbeat_age_seconds = self._heartbeat_age_seconds(data, now=now)
            if (
                heartbeat_age_seconds >= warning_window_seconds
                and self._should_log_claim_event(
                    job_id=doc.id,
                    event=self._CLAIM_LOG_EVENT_STALE,
                    now=now,
                    suppression_window_seconds=warning_window_seconds,
                )
            ):
                logger.warning(
                    "Research job %s appears stale after %.1fs without heartbeat; attempting reclaim.",
                    doc.id,
                    heartbeat_age_seconds,
                )
            if not self._is_research_job_running_stale(
                data,
                now=now,
                stale_timeout_seconds=stale_timeout_seconds,
            ):
                continue

            try:
                claimed_job = self._claim_research_job_document_sync(
                    doc,
                    worker_id=worker_id,
                    now=now,
                    lease_duration_seconds=lease_duration_seconds,
                    stale_timeout_seconds=stale_timeout_seconds,
                )
            except Exception:
                if self._should_log_claim_event(
                    job_id=doc.id,
                    event=self._CLAIM_LOG_EVENT_ERROR,
                    now=now,
                    suppression_window_seconds=warning_window_seconds,
                ):
                    logger.exception(
                        "Unexpected failure while attempting to reclaim research job %s.",
                        doc.id,
                    )
                continue
            if not isinstance(claimed_job, dict):
                continue

            claimed.append(claimed_job)
            if len(claimed) >= limit:
                break

        if len(claimed) >= limit:
            return claimed

        for doc in queued_query.stream():
            data = doc.to_dict() or {}
            next_run = self._as_datetime(data.get("nextRunAt")) or now
            if next_run > now:
                continue

            try:
                claimed_job = self._claim_research_job_document_sync(
                    doc,
                    worker_id=worker_id,
                    now=now,
                    lease_duration_seconds=lease_duration_seconds,
                    stale_timeout_seconds=stale_timeout_seconds,
                )
            except Exception:
                if self._should_log_claim_event(
                    job_id=doc.id,
                    event=self._CLAIM_LOG_EVENT_ERROR,
                    now=now,
                    suppression_window_seconds=warning_window_seconds,
                ):
                    logger.exception(
                        "Unexpected failure while attempting to claim queued research job %s.",
                        doc.id,
                    )
                continue
            if not isinstance(claimed_job, dict):
                continue

            claimed.append(claimed_job)
            if len(claimed) >= limit:
                break

        return claimed

    async def update_research_job_progress(
        self,
        job_id: str,
        current_node: str,
        progress_message: str,
        status: str = "running",
        expected_worker_id: str | None = None,
        progress_details: dict[str, Any] | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._update_research_job_progress_sync,
            job_id,
            current_node,
            progress_message,
            status,
            expected_worker_id,
            progress_details,
        )

    def _update_research_job_progress_sync(
        self,
        job_id: str,
        current_node: str,
        progress_message: str,
        status: str = "running",
        expected_worker_id: str | None = None,
        progress_details: dict[str, Any] | None = None,
    ) -> bool:
        next_status = str(status or "running").strip().lower()
        if next_status not in {"queued", "running", "completed", "failed"}:
            next_status = "running"

        now = datetime.now(timezone.utc)
        return self._update_research_job_if_owned_sync(
            job_id,
            update_payload={
                "status": next_status,
                "currentNode": str(current_node or "").strip() or None,
                "progressMessage": str(progress_message or "").strip() or None,
                "progressDetails": progress_details if isinstance(progress_details, dict) else None,
                "updatedAt": now,
            },
            expected_worker_id=expected_worker_id,
            allowed_statuses={"running"} if expected_worker_id is not None else None,
        )

    async def update_research_job_checkpoint(
        self,
        job_id: str,
        graph_state: dict[str, Any],
        resume_from_node: str | None,
        expected_worker_id: str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._update_research_job_checkpoint_sync,
            job_id,
            graph_state,
            resume_from_node,
            expected_worker_id,
        )

    def _update_research_job_checkpoint_sync(
        self,
        job_id: str,
        graph_state: dict[str, Any],
        resume_from_node: str | None,
        expected_worker_id: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        normalized_resume = str(resume_from_node or "").strip() or None
        payload = {
            "graphState": graph_state if isinstance(graph_state, dict) else {},
            "resumeFromNode": normalized_resume,
            "updatedAt": now,
        }
        return self._update_research_job_if_owned_sync(
            job_id,
            update_payload=payload,
            expected_worker_id=expected_worker_id,
            allowed_statuses={"running"} if expected_worker_id is not None else None,
        )

    async def mark_research_job_completed(
        self,
        job_id: str,
        result_text: str,
        expected_worker_id: str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._mark_research_job_completed_sync,
            job_id,
            result_text,
            expected_worker_id,
        )

    def _mark_research_job_completed_sync(
        self,
        job_id: str,
        result_text: str,
        expected_worker_id: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        return self._update_research_job_if_owned_sync(
            job_id,
            update_payload={
                "status": "completed",
                "currentNode": "completed",
                "progressMessage": progress_message_for_node("completed"),
                "progressDetails": None,
                "resumeFromNode": None,
                "updatedAt": now,
                "completedAt": now,
                "workerId": None,
                "lastHeartbeatAt": now,
                "leaseExpiresAt": None,
                "error": None,
                "resultText": str(result_text or ""),
            },
            expected_worker_id=expected_worker_id,
            allowed_statuses={"running"} if expected_worker_id is not None else None,
        )

    async def mark_research_job_failed(
        self,
        job_id: str,
        error_message: str,
        attempts: int,
        resume_from_node: str | None = None,
        expected_worker_id: str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._mark_research_job_failed_sync,
            job_id,
            error_message,
            attempts,
            resume_from_node,
            expected_worker_id,
        )

    def _mark_research_job_failed_sync(
        self,
        job_id: str,
        error_message: str,
        attempts: int,
        resume_from_node: str | None = None,
        expected_worker_id: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        normalized_resume = str(resume_from_node or "").strip() or None
        return self._update_research_job_if_owned_sync(
            job_id,
            update_payload={
                "status": "failed",
                "currentNode": "failed",
                "progressMessage": progress_message_for_node("failed"),
                "progressDetails": None,
                "updatedAt": now,
                "failedAt": now,
                "workerId": None,
                "lastHeartbeatAt": now,
                "leaseExpiresAt": None,
                "attempts": int(max(attempts, 0)),
                "error": str(error_message or "Research processing failed."),
                "resumeFromNode": normalized_resume,
            },
            expected_worker_id=expected_worker_id,
            allowed_statuses={"running"} if expected_worker_id is not None else None,
        )

    async def requeue_research_job(
        self,
        job_id: str,
        attempts: int,
        error_message: str,
        delay_seconds: float,
        resume_from_node: str | None = None,
        expected_worker_id: str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._requeue_research_job_sync,
            job_id,
            attempts,
            error_message,
            delay_seconds,
            resume_from_node,
            expected_worker_id,
        )

    def _requeue_research_job_sync(
        self,
        job_id: str,
        attempts: int,
        error_message: str,
        delay_seconds: float,
        resume_from_node: str | None = None,
        expected_worker_id: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        next_run = now + timedelta(seconds=max(float(delay_seconds or 0.0), 0.0))
        normalized_resume = str(resume_from_node or "").strip() or None
        return self._update_research_job_if_owned_sync(
            job_id,
            update_payload={
                "status": "queued",
                "currentNode": "queued",
                "progressMessage": progress_message_for_node("queued"),
                "progressDetails": None,
                "resumeFromNode": normalized_resume,
                "updatedAt": now,
                "nextRunAt": next_run,
                "workerId": None,
                "lastHeartbeatAt": now,
                "leaseExpiresAt": None,
                "attempts": int(max(attempts, 0)),
                "error": str(error_message or "Research processing failed."),
            },
            expected_worker_id=expected_worker_id,
            allowed_statuses={"running"} if expected_worker_id is not None else None,
        )

    async def heartbeat_research_job(
        self,
        job_id: str,
        worker_id: str,
        lease_duration_seconds: float,
    ) -> bool:
        return await asyncio.to_thread(
            self._heartbeat_research_job_sync,
            job_id,
            worker_id,
            lease_duration_seconds,
        )

    def _heartbeat_research_job_sync(
        self,
        job_id: str,
        worker_id: str,
        lease_duration_seconds: float,
    ) -> bool:
        now = datetime.now(timezone.utc)
        lease_expires_at = now + timedelta(seconds=max(float(lease_duration_seconds or 0.0), 1.0))
        return self._update_research_job_if_owned_sync(
            job_id,
            update_payload={
                "updatedAt": now,
                "lastHeartbeatAt": now,
                "leaseExpiresAt": lease_expires_at,
            },
            expected_worker_id=worker_id,
            allowed_statuses={"running"},
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
        settings = get_settings()
        now = datetime.now(timezone.utc)
        stale_timeout_seconds = max(
            float(settings.research_job_stale_timeout_seconds or 0.0),
            0.0,
        )

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
            status_priority = 2
            if status == "running" and self._is_research_job_running_stale(
                payload,
                now=now,
                stale_timeout_seconds=stale_timeout_seconds,
            ):
                status_priority = 0
            elif status != "running":
                status_priority = 1
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
            "progressDetails": raw.get("progressDetails") if isinstance(raw.get("progressDetails"), dict) else None,
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
