import asyncio
from langchain_core.tools import tool, BaseTool
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from playwright.async_api import Browser

from custom_search import CustomSearch
from scrape import Scrape
from database import Database
from nodes import Nodes

class Tools:

    def __init__(self, session_id: str, database: Database, browser: Browser):
        self.__search = CustomSearch()
        self.__scrape = Scrape(browser)
        self.__database = database
        self.__session_id = session_id
        self.__model = ChatGoogleGenerativeAI(model = "models/gemini-flash-lite-latest")
        self.__nodes = Nodes()

    async def __get_doc_summary(self, document: Document) -> str:
        summary = await self.__model.ainvoke(self.__nodes.generate_rolling_summary(document.page_content))
        return summary.text.strip()

    async def web_search_tool(self, query: str) -> str:
        """Web Search tool to access documents from the web based on the given search query"""
        try:
            __urls = await self.__search.search(query, 5)
            if not __urls:
                return "No search results found."

            documents = await asyncio.gather(*[self.__scrape.scrape(url, title) for url, title in __urls.items()])
            documents = [doc for doc in documents if doc is not None and doc.page_content is not None and doc.page_content.strip() != ""]
            if not documents:
                return "Search results were found, but no scrapeable page content was extracted."

            await self.__database.add_data(self.__session_id, documents)
            summaries = await asyncio.gather(*[self.__get_doc_summary(doc) for doc in documents])
            return "\n----------------\n".join([f"Title: {doc.metadata.get('title', 'None')}\nContent:{summaries[_]}\nSource: {doc.metadata.get('source', 'None')}" for _, doc in enumerate(documents)])
        except Exception as e:
            return f"An error occured: {str(e)}"
    
    async def url_search_tool(self, url: str) -> str:
        """URL Search tool to access documents from the web based on the given URL"""
        try:
            document = await self.__scrape.scrape(url)
            if document is not None and document.page_content is not None and document.page_content.strip() != "":
                await self.__database.add_data(self.__session_id, [document])
                return f"Title: {document.metadata.get('title', 'None')}\nContent:{document.page_content}\nSource: {document.metadata.get('source', 'None')}"
            else:
                return "No content found at the provided URL."
        except Exception as e:
            return f"An error occured: {str(e)}"
    
    async def vector_search_tool(self, query: str) -> str:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        try:
            documents = await self.__database.vector_search(session_id=self.__session_id, query=query)
            return "\n----------------\n".join([f"Title: {doc.metadata.get('title', 'None')}\nContent:{doc.page_content}\nSource: {doc.metadata.get('source', 'None')}" for doc in documents])
        except Exception as e:
            return f"An error occured: {str(e)}"
    
    def return_tools(self) -> list[BaseTool]:
        return [tool(self.vector_search_tool), tool(self.web_search_tool), tool(self.url_search_tool)]
