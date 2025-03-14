from database import database
from langchain_core.documents import Document

class tools:

    def __init__(self, session_id: str):
        self.__database = database(session_id)

    def vector_search_tool(self, query: str) -> list[Document]:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        return self.__database.search_data(query)
    
    def add_human_message(self, message: str) -> None:
        self.__database.add_human_message(message)

    def add_ai_message(self, message: str) -> None:
        self.__database.add_ai_message(message)

    def add_message(self, message) -> None:
        self.__database.add_message(message)

    def close_tools(self) -> None:
        self.__database.close_connection()
        del self.__database