from bs4 import BeautifulSoup
from playwright.async_api import Browser, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from langchain_core.documents import Document
import asyncio

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
    
    async def _get_context(self):
        if self._context and not self._context.is_closed():
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

    async def scrape(self, url: str, title: str = None) -> Document | None:
        try:
            context = await self._get_context()
            page = await context.new_page()
            try:
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_selector("body", timeout=60000)

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
                await page.close()
        except PlaywrightTimeoutError:
            print(f"Timeout error while accessing {url}")
            return None
        except Exception as exc:
            print(f"Error scraping {url}: {exc}")
            return None