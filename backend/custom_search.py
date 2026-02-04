import os, httpx
from typing import Any

class CustomSearch:
    def __init__(self):
        self.__api_key = os.getenv("GEMINI_API_KEY")
        self.__search_engine_id = os.getenv("SEARCH_ENGINE_ID")
        self.__base_url = "https://www.googleapis.com/customsearch/v1"

        timeout_s = 20.0
        self.__client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))

    async def aclose(self) -> None:
        await self.__client.aclose()
    
    async def search(self, query: str, num: int) -> dict[str, str]:
        try:
            if not self.__api_key:
                raise RuntimeError("Missing API key for Custom Search (set GEMINI_API_KEY)")
            if not self.__search_engine_id:
                raise RuntimeError("Missing SEARCH_ENGINE_ID for Custom Search")
            
            params = {
                "key": self.__api_key,
                "cx": self.__search_engine_id,
                "lr": "lang_en",
                "num": int(num),
                "q": query,
                "c2coff": 1,
                "orTerms": "Research Paper|Article|Research Article|Research|Latest|News",
                "hl": "en",
            }
            resp = await self.__client.get(self.__base_url, params=params)
            resp.raise_for_status()
            search: dict[str, Any] = resp.json()

            if "items" not in search or not isinstance(search["items"], list):
                print("No search results found.")
                return {}

            items = search["items"]
            urls: dict[str, str] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                link = item.get("link")
                title = item.get("title")
                if isinstance(link, str) and link and isinstance(title, str) and title:
                    urls[link] = title
            return urls
        
        except Exception as error:
            raise error