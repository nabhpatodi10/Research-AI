import asyncio
import logging
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage
from playwright.async_api import Browser

from database import Database
from graph import ResearchGraph
from research_progress import progress_message_for_node
from settings import get_settings
from structures import CompleteDocument


logger = logging.getLogger(__name__)


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

    async def run(
        self,
        job: dict[str, Any],
        progress_callback: Any = None,
        checkpoint_callback: Any = None,
    ) -> str:
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
            progress_callback=progress_callback,
        )
        saved_graph_state = job.get("graphState")
        if not isinstance(saved_graph_state, dict):
            saved_graph_state = {}
        resume_from_node = str(job.get("resumeFromNode") or "").strip() or None
        result = await graph.run_resumable(
            research_idea=research_idea,
            graph_state=saved_graph_state,
            resume_from_node=resume_from_node,
            checkpoint_callback=checkpoint_callback,
        )
        final_text = self._extract_document_text(result.get("final_document")).strip()
        if not final_text:
            raise ValueError("Research workflow returned empty content.")

        await self._database.add_messages(session_id, [AIMessage(content=final_text)])
        return final_text


class ResearchBackgroundWorker:
    def __init__(self, database: Database, browser: Browser):
        settings = get_settings()
        self._database = database
        self._worker_id = str(uuid4())
        self._poll_interval_seconds = settings.research_background_poll_interval_seconds
        self._batch_size = settings.research_background_batch_size
        self._max_retries = settings.research_background_max_retries
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

        resume_from_node = str(job.get("resumeFromNode") or "").strip() or None
        current_node_tracker = resume_from_node or "preparing"

        await self._database.set_user_session_active_task_status(
            user_id=user_id,
            session_id=session_id,
            task_id=job_id,
            status="running",
        )
        await self._database.update_research_job_progress(
            job_id=job_id,
            current_node=current_node_tracker,
            progress_message=progress_message_for_node(current_node_tracker),
            status="running",
        )

        try:
            async def _progress(node_name: str) -> None:
                nonlocal current_node_tracker
                current_node_tracker = str(node_name or "").strip() or current_node_tracker
                await self._database.update_research_job_progress(
                    job_id=job_id,
                    current_node=node_name,
                    progress_message=progress_message_for_node(node_name),
                    status="running",
                )

            async def _checkpoint(
                completed_node: str,
                graph_state: dict[str, Any],
                next_node: str | None,
            ) -> None:
                await self._database.update_research_job_checkpoint(
                    job_id=job_id,
                    graph_state=graph_state,
                    resume_from_node=next_node,
                )

            result_text = await self._execution_service.run(
                job,
                progress_callback=_progress,
                checkpoint_callback=_checkpoint,
            )
            await self._database.mark_research_job_completed(job_id=job_id, result_text=result_text)
            await self._database.clear_user_session_active_task_if_matches(
                user_id=user_id,
                session_id=session_id,
                task_id=job_id,
            )
            logger.info("Completed research job %s for session %s.", job_id, session_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            next_attempt = attempts + 1
            if next_attempt >= self._max_retries:
                await self._database.mark_research_job_failed(
                    job_id=job_id,
                    error_message=str(error),
                    attempts=next_attempt,
                    resume_from_node=current_node_tracker,
                )
                await self._database.clear_user_session_active_task_if_matches(
                    user_id=user_id,
                    session_id=session_id,
                    task_id=job_id,
                )
                logger.error(
                    "Job %s failed permanently after %s attempts: %s",
                    job_id,
                    next_attempt,
                    error,
                )
                return

            retry_delay_seconds = min(180, 10 * (2 ** (next_attempt - 1)))
            await self._database.requeue_research_job(
                job_id=job_id,
                attempts=next_attempt,
                error_message=str(error),
                delay_seconds=retry_delay_seconds,
                resume_from_node=current_node_tracker,
            )
            await self._database.set_user_session_active_task_status(
                user_id=user_id,
                session_id=session_id,
                task_id=job_id,
                status="queued",
            )
            logger.warning(
                "Requeued job %s attempt %s after error: %s",
                job_id,
                next_attempt,
                error,
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
                    logger.exception("Research worker loop error: %s", error)
                    await asyncio.sleep(self._poll_interval_seconds)
        finally:
            if not active_tasks:
                return
            for task in active_tasks:
                task.cancel()
            await asyncio.gather(*active_tasks, return_exceptions=True)
