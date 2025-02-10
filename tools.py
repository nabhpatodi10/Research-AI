from database import database
from search import search

from langchain.tools import tool

class tools:

    __database: database
    __search: search

    def __init__(self):
        self.__database = database()
        self.__search = search()

    @tool
    def web_search_tool(self, query: str) -> list:
        """Web search tool to search the internet for information based on the given search query"""
        documents = self.__search.search_results(query)
        self.__database.add_data(documents)
        return documents
    
    @tool
    def vector_search_tool(self, query: str) -> list:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        documents = self.__database.search_data(query)
        return documents
    
    def __del__(self):
        del self.__database
        del self.__search