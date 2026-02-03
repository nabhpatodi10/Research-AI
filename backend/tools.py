from langchain_core.documents import Document
from langchain_core.tools import tool, BaseTool

from chains import Chains
from database import Database

class Tools:

    def __init__(self, session_id: str, database: Database, browser):
        self.__chains = Chains(database, browser)
        self.__database = database
        self.__session_id = session_id

    async def web_search_tool(self, query: str) -> str:
        """Web Search tool to access documents from the web based on the given search query"""
        __urls = await self.__chains.web_search({query: 5})
        documents = await self.__chains.web_scrape(__urls)
        return "\n----------------\n".join([f"Title: {doc.metadata.get('title', 'None')}\nContent:{doc.page_content}\nSource: {doc.metadata.get('source', 'None')}" for doc in documents])
    
    async def vector_search_tool(self, query: str) -> str:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        documents = await self.__database.vector_search(session_id=self.__session_id, query=query)
        return "\n----------------\n".join([f"Title: {doc.metadata.get('title', 'None')}\nContent:{doc.page_content}\nSource: {doc.metadata.get('source', 'None')}" for doc in documents])
    
    def return_tools(self) -> list[BaseTool]:
        return [tool(self.vector_search_tool), tool(self.web_search_tool)]