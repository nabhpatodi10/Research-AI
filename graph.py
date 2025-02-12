from typing import TypedDict, Annotated
from pydantic import Field
import operator
from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage
from langgraph.graph import StateGraph, END
from langchain_core.documents import Document

from tools import tools
from nodes import Nodes

class GraphSchema(TypedDict):
    topic: str
    output_format: str
    plan: list[str]
    queries: Annotated[list[AnyMessage], operator.add]
    index: int
    documents: list[Document]

class QuerySchema(TypedDict):
    search_queries: list[str] = Field(description = "A list of all the search queries which have to be used to search for information on the internet.")

class PlanSchema(TypedDict):
    plan: list[str] = Field(description = "A list of all the headings, topics and sub-topics which are to be included in the final document and under which the entire content has to be organised.")

class BooleanSchema(TypedDict):
    check: bool = Field(description = "A boolean value given as output based on which further events occur.")

class ContentSchema(TypedDict):
    heading: str = Field(description = "The heading, topic or sub-topic under which the content is being generated.")
    content: str = Field(description = "The content which is being generated for the given heading, topic or sub-topic.")

class Graph:

    def __init__(self, model):
        self.__tools = tools()
        self.__nodes = Nodes()
        graph = StateGraph(GraphSchema)
        graph.add_node("generate_search_queries", self.__generate_search_queries)
        graph.add_node("plan_document", self.__plan_document)
        graph.add_node("retrieve_documents", self.__retrieve_documents)
        graph.add_node("generate_content", self.__generate_content)
        graph.add_conditional_edges(
            "generate_search_queries",
            self.__planning_check,
            {True : "plan_document", False : "retrieve_documents"}
        )
        graph.add_conditional_edges(
            "retrieve_documents",
            self.__information_check,
            {True : "generate_content", False : "generate_search_queries"}
        )
        graph.add_conditional_edges(
            "generate_content",
            self.__heading_left_check,
            {True : "retrieve_documents", False : END}
        )
        graph.add_edge("plan_document", "retrieve_documents")
        graph.set_entry_point("generate_search_queries")
        self.graph = graph.compile()
        self.__model = model

    def __generate_search_queries(self, state: GraphSchema):

        queries = self.__model.with_structured_output(QuerySchema).invoke(self.__nodes.generate_search_queries(state["topic"], state["output_format"]))
        
        for query in queries["search_queries"]:
            self.__tools.web_search_tool(query)

        print(queries["search_queries"])

        return {"queries" : queries["search_queries"]}

    def __plan_document(self, state: GraphSchema):
        if len(state["plan"]) > 0:
            messages = self.__nodes.next_plan_document(state["topic"], state["output_format"], state["queries"], state["plan"], state["index"])
        else:
            messages = self.__nodes.first_plan_document(state["topic"], state["output_format"], state["queries"])

        plan = self.__model.with_structured_output(PlanSchema).invoke(messages)

        print(plan["plan"])

        return {"plan" : plan["plan"]}
    
    def __retrieve_documents(self, state: GraphSchema):
        
        queries = self.__model.with_structured_output(QuerySchema).invoke(self.__nodes.generate_vector_queries(state["topic"], state["output_format"], state["plan"][state["index"]]))

        documents = []

        for query in queries["search_queries"]:
            docs = self.__tools.vector_search_tool(query)
            for doc in docs:
                if doc not in documents:
                    documents.append(doc)

        print("Documents Retrieved")

        return {"documents" : documents}
    
    def __generate_content(self, state: GraphSchema):
        
        documents = state["documents"]

        information = ""
        for document in documents:
            information += f"\n{document.page_content}"

        content = self.__model.with_structured_output(ContentSchema).invoke(self.__nodes.generate_content(state["topic"], state["output_format"], state["plan"][state["index"]], information))

        self.__tools.write_in_file_tool(content.heading + "\n" + content.content)

        index = state["index"]

        print(f"Content generated for index: {index}")

        return {"index" : index + 1}
    
    def __planning_check(self, state: GraphSchema) -> bool:
        if len(state["plan"]) > 0:
            return self.__model.with_structured_output(BooleanSchema).invoke(self.__nodes.planning_check(state["topic"], state["output_format"], state["queries"], state["plan"]))
        else:
            return True
        
    def __information_check(self, state: GraphSchema) -> bool:
        information = ""
        for document in state["documents"]:
            information += f"\n{document.page_content}"

        return self.__model.with_structured_output(BooleanSchema).invoke(self.__nodes.information_check(state["topic"], state["output_format"], state["plan"][state["index"]], information))
    
    def __heading_left_check(self, state: GraphSchema) -> bool:
        return state["index"] < len(state["plan"])