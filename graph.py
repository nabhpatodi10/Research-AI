from typing import TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langchain_core.documents import Document

from tools import tools

class GraphSchema(TypedDict):
    topic: str
    output_format: str
    plan: list[str]
    index: int
    documents: list[Document]

class QuerySchema(BaseModel):
    search_queries: list[str] = Field(description = "A list of all the search queries which have to be used to search for information on the internet.")

class PlanSchema(BaseModel):
    plan: list[str] = Field(description = "A list of all the headings, topics and sub-topics which are to be included in the final document and under which the entire content has to be organised.")

class BooleanSchema(BaseModel):
    check: bool = Field(description = "A boolean value given as output based on which further events occur.")

class ContentSchema(BaseModel):
    heading: str = Field(description = "The heading, topic or sub-topic under which the content is being generated.")
    content: str = Field(description = "The content which is being generated for the given heading, topic or sub-topic.")

class Graph:

    def __init__(self, model):
        self.__tools = tools()
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
        messages = [
            SystemMessage(
                content = """"""
            ),
            HumanMessage(
                content = """"""
            )
        ]

        queries = self.__model.with_structured_output(QuerySchema).invoke(messages)
        
        for query in queries.search_queries:
            self.__tools.web_search_tool(query)

    def __plan_document(self, state: GraphSchema):
        if state["plan"]:
            messages = [
                SystemMessage(
                    content = """"""
                ),
                HumanMessage(
                    content = """"""
                )
            ]
        else:
            messages = [
                SystemMessage(
                    content = """"""
                ),
                HumanMessage(
                    content = """"""
                )
            ]

        plan = self.__model.with_strctured_output(PlanSchema).invoke(messages)

        return {"plan" : plan.plan}
    
    def __retrieve_documents(self, state: GraphSchema):
        messages = [
            SystemMessage(
                content = """"""
            ),
            HumanMessage(
                content = """"""
            )
        ]

        queries = self.__model.with_structured_output(QuerySchema).invoke(messages)

        documents = set([])

        for query in queries.search_queries:
            docs = self.__tools.vector_search_tool(query)
            for doc in docs:
                documents.add(doc)

        return {"documents" : list(documents)}
    
    def __generate_content(self, state: GraphSchema):
        documents = state["documents"]

        messages = [
            SystemMessage(
                content = """"""
            ),
            HumanMessage(
                content = """"""
            )
        ]

        content = self.__model.with_structured_output(ContentSchema).invoke(messages)

        self.__tools.write_in_file_tool(content.heading + "\n" + content.content)

        index = state["index"]
        return {"index" : index + 1}
    
    def __planning_check(self, state: GraphSchema) -> bool:
        if state["plan"]:
            messages = [
                SystemMessage(
                    content = """"""
                ),
                HumanMessage(
                    content = """"""
                )
            ]
            return self.__model.with_structured_output(BooleanSchema).invoke(messages)
        else:
            return True
        
    def __information_check(self, state: GraphSchema) -> bool:
        information = "The following is the information we have about the given heading:"
        for document in state["documents"]:
            information += f"\n{document.page_content}"

        messages = [
            SystemMessage(
                content = """"""
            ),
            HumanMessage(
                content = """"""
            )
        ]

        return self.__model.with_structured_output(BooleanSchema).invoke(messages)
    
    def __heading_left_check(self, state: GraphSchema) -> bool:
        return state["index"] < len(state["plan"])