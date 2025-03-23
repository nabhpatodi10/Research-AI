import time

from langchain.schema.runnable import RunnableParallel, RunnableLambda
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from openai import RateLimitError

from nodes import Nodes
from tools import tools
from custom_search import CustomSearch
from scrape import Scrape
from expertagent import ExpertAgent
import structures

class Chains:

    __model: ChatOpenAI
    __node: Nodes
    __tool: tools
    __customSearch: CustomSearch
    __scrape: Scrape

    def __init__(self, tools: tools):
        self.__model = ChatOpenAI(model = "gpt-4o-mini")
        self.__node = Nodes()
        self.__customSearch = CustomSearch()
        self.__scrape = Scrape()
        self.__tool = tools

    def web_search(self, queries: dict[str, int]) -> dict[str, str]:
        __chains = []
        for i in range(len(queries)):
            __chains.append(RunnableLambda(lambda input, i=i: self.__customSearch.search(input[f"chain{i}"][0], input[f"chain{i}"][1])))

        __final_chain = RunnableParallel({f"chain{i}" : chain for i, chain in enumerate(__chains)})

        try:
            __outputs = __final_chain.invoke({f"chain{i}" : (query, num) for i, (query, num) in enumerate(queries.items())})
            __urls = {}
            for output in __outputs:
                __urls.update(__outputs[output])
                for i in __outputs[output]:
                    print("Searched:", i)
            return __urls                

        except Exception as error:
            raise error
        
    def web_scrape(self, urls: dict[str, str]) -> list[Document]:
        __chains = []
        for i in range(len(urls)):
            __chains.append(RunnableLambda(lambda input, i=i: self.__scrape.scrape(input[f"chain{i}"][0], input[f"chain{i}"][1])))
        
        __final_chain = RunnableParallel({f"chain{i}" : chain for i, chain in enumerate(__chains)})

        try:
            __documents = __final_chain.invoke({f"chain{i}" : (url, title) for i, (url, title) in enumerate(urls.items())})
            __finaldocs = []
            for i in __documents:
                if __documents[i]:
                    __finaldocs.append(__documents[i])
            print(f"\n\nTotal Documents: {len(__finaldocs)}\n\n")
            return __finaldocs
        
        except Exception as error:
            raise error

    def get_document_outline(self, documents: list[Document]) -> str:
        batch = []
        for document in documents:
            batch.append(self.__node.get_outline(document))
        
        try:
            __outlines = self.__model.with_structured_output(schema=structures.Outline, method="json_schema").batch(batch)
        except RateLimitError:
            time.sleep(10)
            __outlines = self.__model.with_structured_output(schema=structures.Outline, method="json_schema").batch(batch[len(batch)//2:])
            __outlines += self.__model.with_structured_output(schema=structures.Outline, method="json_schema").batch(batch[:len(batch)//2])

        __stroutlines = ""
        for i in __outlines:
            __stroutlines += i.as_str + "\n\n--------------------------------\n\n"

        return __stroutlines
    
    def generate_perspective_content(self, perspectives: structures.Perspectives, topic: str, output_format: str, outline: str, section: str) -> list[str]:
        __chains = []

        @tool
        def __vector_search_tool(query: str) -> list[Document]:
            """Vector Store Search tool to access documents from the vector store based on the given search query"""
            return self.__tool.vector_search_tool(query)
        
        def __return_dict(messages) -> dict:
            return {"messages" : messages}

        for i in range(len(perspectives.editors)):
            __agent = ExpertAgent([__vector_search_tool])
            __chains.append(RunnableLambda(lambda _, i=i : self.__node.perspective_agent(perspectives.editors[i].persona, topic, output_format, outline, section)) | __return_dict | __agent.graph)

        __final_chain = RunnableParallel({f"chain{i}" : chain for i, chain in enumerate(__chains)})

        try:
            __results = __final_chain.invoke({})
        except RateLimitError:
            time.sleep(10)
            __results = __final_chain.invoke({})
            
        __final_result = []
        for i in __results:
            __final_result.append(__results[i]["messages"][-1].content)

        return __final_result