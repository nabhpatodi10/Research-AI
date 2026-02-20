import asyncio
from typing import Any
from uuid import uuid4

from database import Database
from pdf_processing_modules.service import PdfProcessingService
from settings import get_settings


class PdfBackgroundWorker:
    def __init__(self, database: Database):
        settings = get_settings()
        self._database = database
        self._worker_id = str(uuid4())
        self._poll_interval_seconds = settings.pdf_background_poll_interval_seconds
        self._max_retries = settings.pdf_background_max_retries
        self._batch_size = settings.pdf_background_batch_size
        self._pdf_service = PdfProcessingService(
            session_id="",
            database=database,
            enable_primary_model=False,
        )

    async def _process_job(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("id") or "").strip()
        session_id = str(job.get("sessionId") or "").strip()
        source_url = str(job.get("sourceUrl") or "").strip()
        title = str(job.get("title") or "").strip() or source_url
        attempts = int(job.get("attempts") or 0)

        if not job_id or not session_id or not source_url:
            if job_id:
                await self._database.mark_pdf_processing_job_failed(
                    job_id=job_id,
                    error_message="Job payload is missing required fields.",
                    attempts=attempts + 1,
                )
            return

        try:
            result = await self._pdf_service.extract_pdf_in_memory(
                url=source_url,
                title=title,
            )
            if result.status != "complete" or not result.text.strip():
                raise ValueError(result.error or "Fallback extraction returned empty text.")

            document = self._pdf_service.build_pdf_document(
                url=source_url,
                title=title,
                text=result.text,
                partial=False,
                extraction_method="in_memory_pdf_parser",
            )
            if document is None:
                raise ValueError("Fallback extraction generated no document content.")

            await self._database.replace_source_data(
                session_id=session_id,
                source_url=source_url,
                documents=[document],
            )
            await self._database.mark_pdf_processing_job_completed(
                job_id=job_id,
                characters=len(result.text),
                page_count=result.total_pages,
            )
            print(f"[pdf-worker] Completed PDF fallback job {job_id} for {source_url}.")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            next_attempt = attempts + 1
            if next_attempt >= self._max_retries:
                await self._database.mark_pdf_processing_job_failed(
                    job_id=job_id,
                    error_message=str(error),
                    attempts=next_attempt,
                )
                print(
                    f"[pdf-worker] Job {job_id} failed permanently after {next_attempt} attempts: {error}"
                )
                return

            retry_delay_seconds = min(300, 15 * (2 ** (next_attempt - 1)))
            await self._database.requeue_pdf_processing_job(
                job_id=job_id,
                attempts=next_attempt,
                error_message=str(error),
                delay_seconds=retry_delay_seconds,
            )
            print(
                f"[pdf-worker] Requeued job {job_id} attempt {next_attempt} "
                f"after error: {error}"
            )

    async def run_forever(self) -> None:
        while True:
            try:
                jobs = await self._database.claim_pdf_processing_jobs(
                    worker_id=self._worker_id,
                    limit=self._batch_size,
                )
                if not jobs:
                    await asyncio.sleep(self._poll_interval_seconds)
                    continue

                for job in jobs:
                    await self._process_job(job)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(f"[pdf-worker] Loop error: {error}")
                await asyncio.sleep(self._poll_interval_seconds)
