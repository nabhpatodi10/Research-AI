from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from langchain_core.documents import Document

class Scrape:

    def scrape(self, url: str, title: str) -> Document:

        try:
            with sync_playwright() as p:
                __browser = p.chromium.launch(headless=True)
                __context = __browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/115.0.0.0 Safari/537.36")
                )
                __page = __context.new_page()
                __page.goto(url, timeout=30000)
                __html = __page.content()
                __soup = BeautifulSoup(__html, "html.parser")
                __text_elements = __soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
                __text = "\n".join([elem.get_text(strip=True) for elem in __text_elements])
                if __text and len(__text) < 1000:
                    return None
                __document = Document(page_content=f"{title}\n\n{__text}",
                                    metadata={"source": url})
                __browser.close()
                return __document
        
        except Exception:
            return None