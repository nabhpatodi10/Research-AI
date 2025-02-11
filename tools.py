from database import database
from search import search

class tools:

    __database: database
    __search: search

    def __init__(self):
        self.__database = database()
        self.__search = search()

    def web_search_tool(self, query: str) -> None:
        """Web search tool to search the internet for information based on the given search query and automatically stores the information in a vector store"""
        documents = self.__search.search_results(query)
        self.__database.add_data(documents)

    def vector_search_tool(self, query: str) -> list:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        documents = self.__database.search_data(query)
        return documents

    def write_in_file_tool(self, content: str) -> None:
        """Use this tool to write the generated content into a text file so that it can be saved."""
        file = open("sample.txt", "a")
        file.write(content)
        file.close()