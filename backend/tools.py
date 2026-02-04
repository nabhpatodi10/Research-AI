import asyncio
from langchain_core.tools import tool, BaseTool
from playwright.async_api import Browser

from custom_search import CustomSearch
from scrape import Scrape
from database import Database

class Tools:

    def __init__(self, session_id: str, database: Database, browser: Browser):
        self.__search = CustomSearch()
        self.__scrape = Scrape(browser)
        self.__database = database
        self.__session_id = session_id

    async def web_search_tool(self, query: str) -> str:
        """Web Search tool to access documents from the web based on the given search query"""
        __urls = await self.__search.search(query, 5)
        documents = await asyncio.gather(*[self.__scrape.scrape(url, title) for url, title in __urls.items()])
        return "\n----------------\n".join([f"Title: {doc.metadata.get('title', 'None')}\nContent:{doc.page_content}\nSource: {doc.metadata.get('source', 'None')}" for doc in documents])
    
    async def vector_search_tool(self, query: str) -> str:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        documents = await self.__database.vector_search(session_id=self.__session_id, query=query)
        return "\n----------------\n".join([f"Title: {doc.metadata.get('title', 'None')}\nContent:{doc.page_content}\nSource: {doc.metadata.get('source', 'None')}" for doc in documents])
    
    def return_tools(self) -> list[BaseTool]:
        return [tool(self.vector_search_tool), tool(self.web_search_tool)]