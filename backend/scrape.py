from bs4 import BeautifulSoup
from playwright.async_api import Browser, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_async
from langchain_core.documents import Document

class Scrape:
    def __init__(self, browser: Browser):
        self.browser = browser

    async def scrape(self, url: str, title: str) -> Document:
        try:
            context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/115.0.0.0 Safari/537.36"
                ),
                bypass_csp=True,
                ignore_https_errors=True
            )
            page = await context.new_page()
            await stealth_async(page)
            await page.goto(url, timeout=60000)
            await page.wait_for_selector("body", timeout=60000)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            text_elements = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
            text = "\n".join([elem.get_text(strip=True) for elem in text_elements])

            await context.close()

            if text and len(text) < 1000:
                return None

            return Document(page_content=f"{title}\n\n{text}", metadata={"source": url})

        except PlaywrightTimeoutError:
            print(f"Timeout error while accessing {url}")
            return None
        except Exception as e:
            print(f"An error occurred while scraping {url}: {e}")
            return None