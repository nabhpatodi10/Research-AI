import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup
from langchain_core.documents import Document
from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from settings import get_settings

if TYPE_CHECKING:
    from pdf_processing import PdfProcessingService


SCRAPE_TIMEOUT_MS = get_settings().scrape_timeout_ms
logger = logging.getLogger(__name__)


@dataclass
class _ContextSlot:
    slot_id: int
    context: BrowserContext
    ref_count: int = 0
    retired: bool = False


def _extract_text_and_title(
    html: str,
    url: str,
    provided_title: str | None,
    page_title: str | None,
) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n", strip=True)

    resolved_title = (
        provided_title
        or page_title
        or (soup.title.string.strip() if soup.title and soup.title.string else None)
        or url
    )

    return resolved_title, text


class Scrape:
    def __init__(self, browser: Any, pdf_processor: "PdfProcessingService | None" = None):
        self.browser = browser
        self._stealth = Stealth()
        self._slot_lock = asyncio.Lock()
        self._slots: dict[int, _ContextSlot] = {}
        self._active_slot_id: int | None = None
        self._next_slot_id = 1
        self._pdf_processor = pdf_processor

    @staticmethod
    def _is_browser_disconnect_error(message: str) -> bool:
        lowered = message.lower()
        return (
            "browser has been closed" in lowered
            or "browser closed" in lowered
            or "connection closed" in lowered
            or "is not connected" in lowered
            or "browser is disconnected" in lowered
            or "target closed" in lowered
        )

    @staticmethod
    def _is_context_closed_error(message: str) -> bool:
        lowered = message.lower()
        return (
            "target page, context or browser has been closed" in lowered
            or "context has been closed" in lowered
            or "target page" in lowered
            or "closed" in lowered
        )

    @staticmethod
    def _is_expected_navigation_error(message: str) -> bool:
        lowered = message.lower()
        return (
            "download is starting" in lowered
            or "err_http2_protocol_error" in lowered
            or "err_connection_reset" in lowered
            or "err_too_many_redirects" in lowered
            or "blockedbyclient" in lowered
        )

    def _browser_is_connected(self) -> bool:
        is_connected = getattr(self.browser, "is_connected", None)
        if not callable(is_connected):
            return True
        try:
            return bool(is_connected())
        except Exception:
            return False

    async def _relaunch_browser(self, reason: str) -> None:
        relaunch = getattr(self.browser, "relaunch", None)
        if not callable(relaunch):
            return
        try:
            maybe_result = relaunch(reason=reason)
        except TypeError:
            maybe_result = relaunch()
        if inspect.isawaitable(maybe_result):
            await maybe_result

    async def _ensure_browser_health(self) -> None:
        if self._browser_is_connected():
            return
        logger.warning("Detected disconnected browser while scraping. Relaunching browser.")
        await self._relaunch_browser("scrape_browser_disconnected")
        if not self._browser_is_connected():
            raise RuntimeError("Browser is disconnected and relaunch did not succeed.")

    async def _configure_context(self, context: BrowserContext) -> None:
        async def _route_handler(route) -> None:
            if route.request.resource_type in {"image", "media", "font", "stylesheet", "other"}:
                await route.abort()
            else:
                await route.continue_()

        await self._stealth.apply_stealth_async(context)
        await context.route("**/*", _route_handler)

    async def _create_context(self) -> BrowserContext:
        for attempt in range(2):
            await self._ensure_browser_health()
            context: BrowserContext | None = None
            try:
                context = await self.browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/115.0.0.0 Safari/537.36"
                    ),
                    bypass_csp=True,
                    ignore_https_errors=True,
                )
                await self._configure_context(context)
                return context
            except Exception as exc:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                if attempt == 0 and self._is_browser_disconnect_error(str(exc)):
                    await self._relaunch_browser("scrape_new_context_disconnected")
                    continue
                raise
        raise RuntimeError("Failed to create scrape browser context.")

    def _get_active_slot_unlocked(self) -> _ContextSlot | None:
        if self._active_slot_id is None:
            return None
        slot = self._slots.get(self._active_slot_id)
        if slot is None or slot.retired:
            self._active_slot_id = None
            return None
        return slot

    async def _get_or_create_active_slot(self) -> _ContextSlot:
        async with self._slot_lock:
            slot = self._get_active_slot_unlocked()
            if slot is not None:
                return slot

        new_context = await self._create_context()
        close_new_context = False

        async with self._slot_lock:
            existing_slot = self._get_active_slot_unlocked()
            if existing_slot is not None:
                close_new_context = True
                selected_slot = existing_slot
            else:
                slot_id = self._next_slot_id
                self._next_slot_id += 1
                selected_slot = _ContextSlot(slot_id=slot_id, context=new_context)
                self._slots[slot_id] = selected_slot
                self._active_slot_id = slot_id

        if close_new_context:
            try:
                await new_context.close()
            except Exception:
                pass

        return selected_slot

    async def _acquire_active_slot(self) -> _ContextSlot:
        while True:
            slot = await self._get_or_create_active_slot()
            async with self._slot_lock:
                current = self._slots.get(slot.slot_id)
                if current is None or current.retired:
                    continue
                current.ref_count += 1
                return current

    async def _release_slot_reference(self, slot_id: int) -> None:
        if slot_id <= 0:
            return
        context_to_close: BrowserContext | None = None
        async with self._slot_lock:
            slot = self._slots.get(slot_id)
            if slot is None:
                return
            if slot.ref_count > 0:
                slot.ref_count -= 1
            if slot.retired and slot.ref_count == 0:
                self._slots.pop(slot_id, None)
                context_to_close = slot.context

        if context_to_close is not None:
            try:
                await context_to_close.close()
            except Exception:
                pass

    async def _retire_slot(self, slot_id: int, reason: str) -> None:
        if slot_id <= 0:
            return
        context_to_close: BrowserContext | None = None
        async with self._slot_lock:
            slot = self._slots.get(slot_id)
            if slot is None:
                return
            slot.retired = True
            if self._active_slot_id == slot_id:
                self._active_slot_id = None
            logger.warning(
                "Retiring scrape context slot=%s reason=%s in_flight=%s",
                slot_id,
                reason,
                slot.ref_count,
            )
            if slot.ref_count == 0:
                self._slots.pop(slot_id, None)
                context_to_close = slot.context

        if context_to_close is not None:
            try:
                await context_to_close.close()
            except Exception:
                pass

    async def _new_page(self) -> tuple[Page, int]:
        last_error: Exception | None = None
        for attempt in range(2):
            slot = await self._acquire_active_slot()
            try:
                page = await slot.context.new_page()
                return page, slot.slot_id
            except Exception as exc:
                await self._release_slot_reference(slot.slot_id)
                message = str(exc)
                if not self._is_context_closed_error(message):
                    raise

                await self._retire_slot(slot.slot_id, reason="new_page_context_closed")
                if self._is_browser_disconnect_error(message):
                    await self._relaunch_browser("new_page_browser_disconnected")

                last_error = exc
                if attempt == 0:
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unable to create a new page for scraping.")

    async def _goto_page(self, page: Page, url: str) -> None:
        # PDF/direct-download links won't render to HTML content in page.goto.
        if url.lower().endswith(".pdf"):
            raise ValueError("PDF URLs are not supported by the HTML scraper.")

        try:
            await page.goto(url, timeout=SCRAPE_TIMEOUT_MS, wait_until="domcontentloaded")
            return
        except asyncio.CancelledError:
            raise
        except PlaywrightTimeoutError:
            raise
        except Exception as exc:
            message = str(exc)
            if "err_http2_protocol_error" in message.lower():
                # Retry once with a lighter wait target for flaky HTTP/2 endpoints.
                await page.goto(url, timeout=SCRAPE_TIMEOUT_MS, wait_until="commit")
                return
            raise

    async def scrape(self, url: str, title: str = None) -> Document | None:
        try:
            if self._pdf_processor is not None and await self._pdf_processor.is_pdf_url(url):
                return await self._pdf_processor.process_pdf_url(url, title)

            last_error: Exception | None = None
            for attempt in range(2):
                page: Page | None = None
                slot_id = 0
                try:
                    page, slot_id = await self._new_page()
                    await self._goto_page(page, url)
                    await page.wait_for_selector("body", timeout=SCRAPE_TIMEOUT_MS)

                    page_title = None
                    try:
                        page_title = await page.title()
                    except Exception:
                        pass

                    html = await page.content()
                    resolved_title, text = await asyncio.to_thread(
                        _extract_text_and_title,
                        html,
                        url,
                        title,
                        page_title,
                    )

                    if not text or len(text) < 500:
                        return None
                    return Document(
                        page_content=f"{resolved_title}\n\n{text}",
                        metadata={"source": url, "title": resolved_title},
                    )
                except asyncio.CancelledError:
                    raise
                except PlaywrightTimeoutError:
                    raise
                except Exception as exc:
                    message = str(exc)
                    if attempt == 0 and self._is_context_closed_error(message):
                        if slot_id > 0:
                            await self._retire_slot(
                                slot_id,
                                reason="scrape_context_closed_during_navigation",
                            )
                        if self._is_browser_disconnect_error(message):
                            await self._relaunch_browser("scrape_navigation_browser_disconnected")
                        last_error = exc
                        continue
                    raise
                finally:
                    if page is not None:
                        try:
                            if not page.is_closed():
                                await page.close()
                        except Exception:
                            pass
                    if slot_id > 0:
                        await self._release_slot_reference(slot_id)

            if last_error is not None:
                raise last_error
            return None
        except asyncio.CancelledError:
            raise
        except PlaywrightTimeoutError:
            logger.warning("Timeout error while accessing %s", url)
            return None
        except ValueError as exc:
            logger.info("Skipping %s: %s", url, exc)
            return None
        except Exception as exc:
            message = str(exc)
            if self._is_expected_navigation_error(message):
                logger.info("Skipping %s: %s", url, message)
                return None
            logger.warning("Error scraping %s: %s", url, exc)
            return None
