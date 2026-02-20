from typing import Any, ClassVar

import httpx

from settings import get_settings


class CustomSearch:
    _client: ClassVar[httpx.AsyncClient | None] = None

    def __init__(self):
        settings = get_settings()
        self.__api_key = settings.gemini_api_key
        self.__search_engine_id = settings.search_engine_id
        self.__base_url = settings.custom_search_base_url

        if CustomSearch._client is None:
            CustomSearch._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.custom_search_timeout_seconds)
            )

        self.__client = CustomSearch._client

    @classmethod
    async def aclose(cls) -> None:
        if cls._client is None:
            return
        await cls._client.aclose()
        cls._client = None
    
    async def search(self, query: str, num: int) -> dict[str, str]:
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
