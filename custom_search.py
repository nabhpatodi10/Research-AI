import os
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from authorisation import authorisation
from playwright.sync_api import sync_playwright

class CustomSearch:
    def __init__(self):
        self.__auth = authorisation()
        self.__creds = self.__auth.cred_token_auth()
        self.__service = build("customsearch", "v1", credentials=self.__creds)
    
    def search(self, query: str, num: int) -> list[Document]:
        try:
            search = self.__service.cse().list(
                cx=os.getenv("SEARCH_ENGINE_ID"),
                lr="lang_en",
                num=num,
                q=query,
                c2coff=1,
                orTerms="Research Paper|Article|Research Article|Research|Latest|News",
                hl="en"
            ).execute()
            items = search["items"]
            documents = []
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/115.0.0.0 Safari/537.36")
                )
                page = context.new_page()
                
                for item in items:
                    try:
                        title = item["title"]
                        url = item["link"]
                        page.goto(url, timeout=30000)
                        html = page.content()
                        soup = BeautifulSoup(html, "html.parser")
                        text_elements = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
                        text = "\n".join([elem.get_text(strip=True) for elem in text_elements])
                        if text and len(text) < 1000:
                            continue
                        document = Document(page_content=f"{title}\n\n{text}",
                                            metadata={"source": url})
                        documents.append(document)
                    except:
                        continue

                browser.close()
            return documents
        
        except Exception as error:
            raise error