from database import database
from search import search

from langchain.tools import tool

__database = database()
__search = search()

@tool
def web_search_tool(query: str) -> list:
    """Web search tool to search the internet for information based on the given search query and automatically stores the information in a vector store"""
    documents = __search.search_results(query)
    __database.add_data(documents)
    return documents

@tool
def vector_search_tool(query: str) -> list:
    """Vector Store Search tool to access documents from the vector store based on the given search query"""
    documents = __database.search_data(query)
    return documents

@tool
def write_in_file_tool(content: str) -> None:
    """Use this tool to write the generated content into a text file so that it can be saved."""
    file = open("sample.txt", "a")
    file.write(content)
    file.close()