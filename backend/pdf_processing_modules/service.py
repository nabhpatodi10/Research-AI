import asyncio
from datetime import datetime, timezone
from typing import Any, ClassVar

import httpx
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from database import Database
from nodes import Nodes
from pdf_processing_modules.helpers import extract_pdf_text_from_bytes
from pdf_processing_modules.models import PdfProcessResult
from settings import build_langsmith_thread_config, get_settings


class PdfProcessingService:
    _http_client: ClassVar[httpx.AsyncClient | None] = None
    _http_client_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(
        self,
        session_id: str,
        database: Database,
        enable_primary_model: bool = True,
    ):
        settings = get_settings()
        self._session_id = session_id
        self._thread_config = build_langsmith_thread_config(session_id)
        self._database = database
        self._probe_timeout_seconds = settings.pdf_probe_timeout_seconds
        self._primary_timeout_seconds = settings.pdf_primary_timeout_seconds
        self._fallback_timeout_seconds = settings.pdf_in_memory_timeout_seconds
        self._min_partial_chars = settings.pdf_min_partial_chars
        self._primary_model = (
            ChatGoogleGenerativeAI(model="models/gemini-flash-lite-latest")
            if enable_primary_model
            else None
        )
        self._nodes = Nodes()

    @classmethod
    async def _get_http_client(cls) -> httpx.AsyncClient:
        if cls._http_client is not None:
            return cls._http_client

        async with cls._http_client_lock:
            if cls._http_client is None:
                settings = get_settings()
                cls._http_client = httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=httpx.Timeout(settings.pdf_http_timeout_seconds),
                )
            return cls._http_client

    @classmethod
    async def aclose_shared_client(cls) -> None:
        if cls._http_client is None:
            return
        await cls._http_client.aclose()
        cls._http_client = None

    @staticmethod
    def _derive_title(url: str, provided_title: str | None) -> str:
        normalized = str(provided_title or "").strip()
        return normalized or url

    @staticmethod
    def _looks_like_pdf_content_type(content_type: str | None) -> bool:
        if not content_type:
            return False
        return "application/pdf" in content_type.lower()

    async def is_pdf_url(self, url: str) -> bool:
        lowered_url = str(url or "").strip().lower()
        if not lowered_url:
            return False

        if ".pdf" in lowered_url:
            return True

        client = await self._get_http_client()
        try:
            head_response = await client.head(
                url,
                timeout=httpx.Timeout(self._probe_timeout_seconds),
            )
            if self._looks_like_pdf_content_type(head_response.headers.get("content-type")):
                return True
            final_url = str(getattr(head_response, "url", "") or "").lower()
            if ".pdf" in final_url:
                return True
        except Exception:
            pass

        try:
            probe_response = await client.get(
                url,
                headers={"Range": "bytes=0-1023"},
                timeout=httpx.Timeout(self._probe_timeout_seconds),
            )
            if self._looks_like_pdf_content_type(probe_response.headers.get("content-type")):
                return True
            final_url = str(getattr(probe_response, "url", "") or "").lower()
            if ".pdf" in final_url:
                return True
        except Exception:
            pass

        return False

    @staticmethod
    def _chunk_text(chunk: Any) -> str:
        text = getattr(chunk, "text", None)
        if isinstance(text, str) and text:
            return text

        message = getattr(chunk, "message", None)
        if message is not None:
            message_text = getattr(message, "text", None)
            if isinstance(message_text, str) and message_text:
                return message_text
            content = getattr(message, "content", None)
            if isinstance(content, str) and content:
                return content
        return ""

    @staticmethod
    def _merge_chunk_text(existing: str, incoming: str) -> str:
        if not incoming:
            return existing
        if not existing:
            return incoming
        if incoming.startswith(existing):
            return incoming
        if existing.endswith(incoming):
            return existing
        return f"{existing}{incoming}"

    async def extract_with_gemini_stream(
        self,
        url: str,
        title: str | None = None,
        timeout_seconds: float | None = None,
    ) -> PdfProcessResult:
        if self._primary_model is None:
            return PdfProcessResult(
                status="failed",
                text="",
                title=self._derive_title(url, title),
                source=url,
                error="Primary model is disabled.",
            )

        resolved_timeout = timeout_seconds or self._primary_timeout_seconds
        resolved_title = self._derive_title(url, title)
        prompt = self._nodes.pdf_url_extraction_prompt(url)

        accumulated = ""
        timed_out = False
        stream = self._primary_model.astream(
            [HumanMessage(content=prompt)],
            config=self._thread_config,
            tools=[{"url_context": {}}],
            tool_choice="required",
        )
        iterator = stream.__aiter__()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + resolved_timeout

        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    timed_out = True
                    break

                try:
                    chunk = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    timed_out = True
                    break

                accumulated = self._merge_chunk_text(accumulated, self._chunk_text(chunk))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return PdfProcessResult(
                status="failed",
                text=accumulated.strip(),
                title=resolved_title,
                source=url,
                error=str(error),
            )
        finally:
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                try:
                    await aclose()
                except Exception:
                    pass

        normalized_text = accumulated.strip()
        if timed_out:
            if normalized_text and len(normalized_text) >= self._min_partial_chars:
                return PdfProcessResult(
                    status="partial_timeout",
                    text=normalized_text,
                    title=resolved_title,
                    source=url,
                    partial=True,
                )
            return PdfProcessResult(
                status="queued",
                text=normalized_text,
                title=resolved_title,
                source=url,
                partial=True,
            )

        if not normalized_text:
            return PdfProcessResult(
                status="failed",
                text="",
                title=resolved_title,
                source=url,
                error="Gemini returned no extractable text.",
            )

        return PdfProcessResult(
            status="complete",
            text=normalized_text,
            title=resolved_title,
            source=url,
            partial=False,
        )

    async def extract_pdf_in_memory(
        self,
        url: str,
        title: str | None = None,
        timeout_seconds: float | None = None,
    ) -> PdfProcessResult:
        resolved_title = self._derive_title(url, title)
        resolved_timeout = timeout_seconds or self._fallback_timeout_seconds
        client = await self._get_http_client()

        try:
            response = await client.get(
                url,
                timeout=httpx.Timeout(resolved_timeout),
            )
            response.raise_for_status()
            pdf_bytes = response.content
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return PdfProcessResult(
                status="failed",
                text="",
                title=resolved_title,
                source=url,
                error=f"Could not fetch PDF bytes: {error}",
            )

        try:
            text, page_count = await asyncio.wait_for(
                asyncio.to_thread(extract_pdf_text_from_bytes, pdf_bytes),
                timeout=resolved_timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return PdfProcessResult(
                status="failed",
                text="",
                title=resolved_title,
                source=url,
                error=f"In-memory PDF parsing failed: {error}",
            )

        normalized = text.strip()
        if not normalized:
            return PdfProcessResult(
                status="failed",
                text="",
                title=resolved_title,
                source=url,
                total_pages=page_count,
                error="PDF does not contain extractable text.",
            )

        return PdfProcessResult(
            status="complete",
            text=normalized,
            title=resolved_title,
            source=url,
            total_pages=page_count,
        )

    def build_pdf_document(
        self,
        url: str,
        title: str | None,
        text: str,
        *,
        partial: bool,
        extraction_method: str,
        timeout_seconds: float | None = None,
        job_id: str | None = None,
    ) -> Document | None:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return None

        resolved_timeout = timeout_seconds or self._primary_timeout_seconds
        resolved_title = self._derive_title(url, title)
        page_content = normalized_text
        if partial:
            page_content = (
                f"[Partial PDF extraction: primary processing timed out after "
                f"{int(resolved_timeout)} seconds. Background completion is queued.]\n\n"
                f"{normalized_text}"
            )

        metadata: dict[str, Any] = {
            "source": url,
            "title": resolved_title,
            "content_type": "application/pdf",
            "is_pdf": True,
            "partial_pdf_content": partial,
            "extraction_method": extraction_method,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        if job_id:
            metadata["pdf_job_id"] = job_id

        return Document(
            page_content=f"{resolved_title}\n\n{page_content}",
            metadata=metadata,
        )

    async def enqueue_background_job(
        self,
        url: str,
        title: str | None,
        reason: str,
        partial_text_available: bool,
    ) -> str | None:
        if not self._session_id:
            return None
        try:
            return await self._database.enqueue_pdf_processing_job(
                session_id=self._session_id,
                source_url=url,
                title=self._derive_title(url, title),
                reason=reason,
                partial_text_available=partial_text_available,
            )
        except Exception as error:
            print(f"[pdf] Failed to enqueue background job for {url}: {error}")
            return None

    async def process_pdf_url(
        self,
        url: str,
        title: str | None = None,
    ) -> Document | None:
        result = await self.extract_with_gemini_stream(
            url=url,
            title=title,
            timeout_seconds=self._primary_timeout_seconds,
        )
        if result.status == "complete":
            return self.build_pdf_document(
                url=url,
                title=result.title,
                text=result.text,
                partial=False,
                extraction_method="gemini_flash_lite_url_context",
            )

        if result.status in {"partial_timeout", "queued"}:
            job_id = await self.enqueue_background_job(
                url=url,
                title=result.title,
                reason="primary_timeout",
                partial_text_available=bool(result.text.strip()),
            )
            if result.text.strip():
                return self.build_pdf_document(
                    url=url,
                    title=result.title,
                    text=result.text,
                    partial=True,
                    extraction_method="gemini_flash_lite_url_context",
                    timeout_seconds=self._primary_timeout_seconds,
                    job_id=job_id,
                )
            return None

        job_id = await self.enqueue_background_job(
            url=url,
            title=result.title,
            reason="primary_failed",
            partial_text_available=bool(result.text.strip()),
        )
        if result.text.strip():
            return self.build_pdf_document(
                url=url,
                title=result.title,
                text=result.text,
                partial=True,
                extraction_method="gemini_flash_lite_url_context",
                timeout_seconds=self._primary_timeout_seconds,
                job_id=job_id,
            )

        print(
            f"[pdf] Primary processing failed for {url}: {result.error}. "
            f"Queued background fallback job: {job_id or 'unavailable'}"
        )
        return None
