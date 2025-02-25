from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.documents import Document

class search:

    __tavilySearch: TavilySearchResults

    def __init__(self):
        self.__tavilySearch = TavilySearchResults(max_results = 10)

    def search_results(self, query: str) -> list[Document]:
        try:
            documents = []
            results = self.__tavilySearch.invoke(query)
            for i in results:
                doc = Document(page_content = i["content"], metadata = {"source" : i["url"]})
                documents.append(doc)
            return documents
        except Exception as error:
            print(i)
            raise error