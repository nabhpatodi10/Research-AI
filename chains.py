import time

from langchain.schema.runnable import RunnableParallel, RunnableLambda
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from openai import RateLimitError

from nodes import Nodes
from tools import tools
from agent import Agent
import structures

class Chains:

    __model: ChatOpenAI
    __node: Nodes
    __tool: tools

    def __init__(self, tools: tools):
        self.__model = ChatOpenAI(model = "gpt-4o-mini")
        self.__node = Nodes()
        self.__tool = tools

    def get_document_outline(self, documents: list[Document]) -> str:
        __chains = []
        for i in range(len(documents)):
            __chains.append(RunnableLambda(lambda input, i=i: self.__node.get_outline(input[f"chain{i}"])) | self.__model.with_structured_output(schema=structures.Outline, method="json_schema"))

        __final_chain = RunnableParallel({f"chain{i}" : chain for i, chain in enumerate(__chains)})

        try:
            __outlines = __final_chain.invoke({f"chain{i}" : doc for i, doc in enumerate(documents)})
        except RateLimitError:
            time.sleep(10)
            __outlines = __final_chain.invoke({f"chain{i}" : doc for i, doc in enumerate(documents[:len(documents)//2])})
            __outlines.update(__final_chain.invoke({f"chain{i+len(documents)//2}" : doc for i, doc in enumerate(documents[len(documents)//2:])}))

        __stroutlines = ""
        for i in __outlines:
            __stroutlines += __outlines[i].as_str + "\n\n--------------------------------\n\n"

        return __stroutlines
    
    def generate_perspective_content(self, perspectives: structures.Perspectives, topic: str, output_format: str, outline: str, section: str) -> list[structures.ContentSection]:
        __chains = []

        @tool
        def __vector_search_tool(query: str) -> list[Document]:
            """Vector Store Search tool to access documents from the vector store based on the given search query"""
            return self.__tool.vector_search_tool(query)
        
        def __return_dict(messages) -> dict:
            return {"messages" : messages}

        for i in range(len(perspectives.editors)):
            __agent = Agent([__vector_search_tool])
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