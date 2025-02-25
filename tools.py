from database import database
from custom_search import custom_search

class tools:

    __database: database
    __search: custom_search

    def __init__(self):
        self.__database = database()
        self.__search = custom_search()

    def web_search_tool(self, query: str) -> None:
        """Web search tool to search the internet for information based on the given search query and automatically stores the information in a vector store"""
        documents = self.__search.search(query)
        self.__database.add_data(documents)

    def vector_search_tool(self, query: str) -> list:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        documents = self.__database.search_data(query)
        return documents

    def write_in_file_tool(self, content: str) -> None:
        """Use this tool to write the generated content into a text file so that it can be saved."""
        file = open("sample.txt", "a")
        file.write(content + "\n")
        file.close()

    def close_tools(self) -> None:
        self.__database.close_connection()
        del self.__database
        del self.__search