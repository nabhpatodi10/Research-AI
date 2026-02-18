import asyncio
import os
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage
from playwright.async_api import Browser

from database import Database
from graph import ResearchGraph
from structures import CompleteDocument


def _to_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _to_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


class ResearchExecutionService:
    def __init__(self, database: Database, browser: Browser):
        self._database = database
        self._browser = browser

    @staticmethod
    def _parse_job_request(job: dict[str, Any]) -> tuple[str, str, str, str]:
        request = job.get("request")
        if not isinstance(request, dict):
            request = {}
        return (
            str(request.get("model") or "pro"),
            str(request.get("researchBreadth") or "medium"),
            str(request.get("researchDepth") or "high"),
            str(request.get("documentLength") or "high"),
        )

    @staticmethod
    def _extract_document_text(final_document: Any) -> str:
        if isinstance(final_document, CompleteDocument):
            return final_document.as_str
        if final_document is None:
            return "The research workflow completed, but no final document was returned."
        return str(final_document)

    async def run(self, job: dict[str, Any]) -> str:
        session_id = str(job.get("sessionId") or "").strip()
        request = job.get("request")
        if not isinstance(request, dict):
            request = {}

        research_idea = str(request.get("researchIdea") or "").strip()
        if not session_id:
            raise ValueError("Research job is missing sessionId.")
        if not research_idea:
            raise ValueError("Research job is missing research idea.")

        model_tier, research_breadth, research_depth, document_length = self._parse_job_request(job)
        graph = ResearchGraph(
            session_id=session_id,
            database=self._database,
            browser=self._browser,
            model_tier=model_tier,
            research_breadth=research_breadth,
            research_depth=research_depth,
            document_length=document_length,
        )
        result = await graph.graph.ainvoke({"research_idea": research_idea})
        final_text = self._extract_document_text(result.get("final_document")).strip()
        if not final_text:
            raise ValueError("Research workflow returned empty content.")

        await self._database.add_messages(session_id, [AIMessage(content=final_text)])
        return final_text


class ResearchBackgroundWorker:
    def __init__(self, database: Database, browser: Browser):
        self._database = database
        self._worker_id = str(uuid4())
        self._poll_interval_seconds = _to_float(
            os.getenv("RESEARCH_BACKGROUND_POLL_INTERVAL_SECONDS"), 1.0
        )
        self._batch_size = _to_int(
            os.getenv("RESEARCH_BACKGROUND_BATCH_SIZE"), 8
        )
        self._max_retries = _to_int(
            os.getenv("RESEARCH_BACKGROUND_MAX_RETRIES"), 2
        )
        self._execution_service = ResearchExecutionService(database=database, browser=browser)

    async def _process_job(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("id") or "").strip()
        user_id = str(job.get("userId") or "").strip()
        session_id = str(job.get("sessionId") or "").strip()
        attempts = int(job.get("attempts") or 0)

        if not job_id or not user_id or not session_id:
            if job_id:
                await self._database.mark_research_job_failed(
                    job_id=job_id,
                    error_message="Job payload is missing required fields.",
                    attempts=attempts + 1,
                )
            return

        await self._database.set_user_session_active_task_status(
            user_id=user_id,
            session_id=session_id,
            task_id=job_id,
            status="running",
        )

        try:
            result_text = await self._execution_service.run(job)
            await self._database.mark_research_job_completed(job_id=job_id, result_text=result_text)
            await self._database.clear_user_session_active_task_if_matches(
                user_id=user_id,
                session_id=session_id,
                task_id=job_id,
            )
            print(f"[research-worker] Completed research job {job_id} for session {session_id}.")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            next_attempt = attempts + 1
            if next_attempt >= self._max_retries:
                await self._database.mark_research_job_failed(
                    job_id=job_id,
                    error_message=str(error),
                    attempts=next_attempt,
                )
                await self._database.clear_user_session_active_task_if_matches(
                    user_id=user_id,
                    session_id=session_id,
                    task_id=job_id,
                )
                print(
                    f"[research-worker] Job {job_id} failed permanently after {next_attempt} attempts: {error}"
                )
                return

            retry_delay_seconds = min(180, 10 * (2 ** (next_attempt - 1)))
            await self._database.requeue_research_job(
                job_id=job_id,
                attempts=next_attempt,
                error_message=str(error),
                delay_seconds=retry_delay_seconds,
            )
            await self._database.set_user_session_active_task_status(
                user_id=user_id,
                session_id=session_id,
                task_id=job_id,
                status="queued",
            )
            print(
                f"[research-worker] Requeued job {job_id} attempt {next_attempt} after error: {error}"
            )

    async def run_forever(self) -> None:
        active_tasks: set[asyncio.Task[None]] = set()
        try:
            while True:
                try:
                    done_tasks = [task for task in active_tasks if task.done()]
                    for task in done_tasks:
                        active_tasks.discard(task)
                        try:
                            _ = task.exception()
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            pass

                    jobs = await self._database.claim_research_jobs(
                        worker_id=self._worker_id,
                        limit=self._batch_size,
                    )
                    for job in jobs:
                        task = asyncio.create_task(self._process_job(job))
                        active_tasks.add(task)

                    if not jobs:
                        await asyncio.sleep(self._poll_interval_seconds)
                    else:
                        await asyncio.sleep(0)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    print(f"[research-worker] Loop error: {error}")
                    await asyncio.sleep(self._poll_interval_seconds)
        finally:
            if not active_tasks:
                return
            for task in active_tasks:
                task.cancel()
            await asyncio.gather(*active_tasks, return_exceptions=True)
