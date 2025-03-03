from database import database
from custom_search import CustomSearch
from langchain_core.documents import Document
from nodes import Nodes

class tools:

    __database: database
    __search: CustomSearch
    __nodes: Nodes

    def __init__(self):
        self.__database = database()
        self.__search = CustomSearch()
        self.__nodes = Nodes()

    def web_search_tool(self, queries: dict) -> list[Document]:
        docs = []
        sources = []
        """Web search tool to search the internet for information based on the given search query and automatically stores the information in a vector store"""
        for i in queries:
            documents = self.__search.search(i, queries[i])
            for doc in documents:
                if doc.metadata["source"] in sources:
                    continue
                docs.append(doc)
                sources.append(doc.metadata["source"])
                print("Searched:", doc.metadata["source"], "\n")
            self.__database.add_data(documents)
        return docs

    def vector_search_tool(self, query: str) -> list[Document]:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        return self.__database.search_data(query)

    def close_tools(self) -> None:
        self.__database.close_connection()
        del self.__database
        del self.__search