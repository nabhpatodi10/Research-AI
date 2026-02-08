import asyncio

from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from langchain_core.documents import Document

SCRAPE_TIMEOUT_MS = 20_000

def _extract_text_and_title(html: str, url: str, provided_title: str | None, page_title: str | None) -> tuple[str, str]:
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
    
    def __init__(self, browser: Browser):
        self.browser = browser
        self._stealth = Stealth()
        self._context = None
        self._context_lock = asyncio.Lock()
    
    async def _get_context(self):
        if self._context is not None:
            return self._context

        async with self._context_lock:
            if self._context is not None:
                return self._context

            self._context = await self.browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/115.0.0.0 Safari/537.36"
                ),
                bypass_csp=True,
                ignore_https_errors=True,
            )
            await self._stealth.apply_stealth_async(self._context)
            await self._context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in {"image", "media", "font", "stylesheet", "other"}
                else route.continue_(),
            )

        return self._context

    async def _reset_context(self):
        async with self._context_lock:
            context = self._context
            self._context = None
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    async def _new_page(self) -> Page:
        context = await self._get_context()
        try:
            return await context.new_page()
        except Exception as exc:
            message = str(exc)
            if "closed" not in message.lower() and "target page" not in message.lower():
                raise

            await self._reset_context()
            refreshed_context = await self._get_context()
            return await refreshed_context.new_page()

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

    async def _goto_page(self, page: Page, url: str):
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
            page = await self._new_page()
            try:
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
            finally:
                try:
                    if not page.is_closed():
                        await page.close()
                except Exception:
                    pass
        except asyncio.CancelledError:
            raise
        except PlaywrightTimeoutError:
            print(f"Timeout error while accessing {url}")
            return None
        except ValueError as exc:
            print(f"Skipping {url}: {exc}")
            return None
        except Exception as exc:
            message = str(exc)
            if self._is_expected_navigation_error(message):
                print(f"Skipping {url}: {message}")
                return None
            print(f"Error scraping {url}: {exc}")
            return None
