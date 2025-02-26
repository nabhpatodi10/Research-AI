from typing import TypedDict, Annotated, List
from pydantic import Field
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph import StateGraph, END
from langchain_core.documents import Document

from tools import tools
from nodes import Nodes

class GraphSchema(TypedDict):
    topic: str
    output_format: str
    plan: List[str]
    queries: Annotated[List[AnyMessage], operator.add]
    index: int
    documents: List[Document]
    need_more_documents: bool
    content: str

class QuerySchema(TypedDict):
    search_queries: List[str] = Field(
        description = "A list of all the search queries as individual elements which have to be used to search for information on the internet.", 
        min_length = 10
    )

class PlanSchema(TypedDict):
    plan: List[str] = Field(
        description = "A list of all the headings, topics and sub-topics which are to be included in the final document and under which the entire content has to be organised."
    )

class BooleanSchema(TypedDict):
    check: bool = Field(
        description = "A boolean value given as output based on which further events occur."
    )

class ContentSchema(TypedDict):
    content: str = Field(
        description = "The content which is being generated for the given heading or sub-heading"
    )

class SummarySchema(TypedDict):
    summary: str = Field(
        description = "The summary of the given part of the research document"
    )

class Graph:

    def __init__(self, model):
        self.tools = tools()
        self.__nodes = Nodes()
        graph = StateGraph(GraphSchema)
        graph.add_node("generate_search_queries", self.__generate_search_queries)
        graph.add_node("plan_document", self.__plan_document)
        graph.add_node("retrieve_documents", self.__retrieve_documents)
        graph.add_node("generate_content", self.__generate_content)
        graph.add_node("write_content", self.__write_content)
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
            self.__content_check,
            {True : "write_content", False : "generate_content"}
        )
        graph.add_conditional_edges(
            "write_content",
            self.__heading_left_check,
            {True : "retrieve_documents", False : END}
        )
        graph.add_edge("plan_document", "retrieve_documents")
        graph.set_entry_point("generate_search_queries")
        self.graph = graph.compile()
        self.__model = model

    def __generate_search_queries(self, state: GraphSchema):

        queries = self.__model.with_structured_output(schema = QuerySchema, method = "json_schema").invoke(self.__nodes.generate_search_queries(state["topic"], state["output_format"]))
        
        for query in queries["search_queries"]:
            self.tools.web_search_tool(query)

        return {"queries" : queries["search_queries"]}

    def __plan_document(self, state: GraphSchema):
        if len(state["plan"]) > 0:
            messages = self.__nodes.next_plan_document(state["topic"], state["output_format"], state["queries"], state["plan"], state["index"])
        else:
            messages = self.__nodes.first_plan_document(state["topic"], state["output_format"], state["queries"])

        plan = self.__model.with_structured_output(schema = PlanSchema, method = "json_schema").invoke(messages)

        return {"plan" : plan["plan"]}
    
    def __retrieve_documents(self, state: GraphSchema):
        
        queries = self.__model.with_structured_output(schema = QuerySchema, method = "json_schema").invoke(self.__nodes.generate_vector_queries(state["topic"], state["output_format"], state["plan"][state["index"]]))

        documents = []

        for query in queries["search_queries"]:
            docs = self.tools.vector_search_tool(query)
            for doc in docs:
                if doc not in documents:
                    documents.append(doc)
                    
        if state["need_more_documents"]:
            documents = state["documents"] + documents

        return {"documents" : documents}
    
    def __generate_content(self, state: GraphSchema):
        
        documents = state["documents"]

        information = ""
        for document in documents:
            information += f"\n{document.page_content}"

        plan = str(state["plan"]).lstrip("[").rstrip("]").replace("'", "")

        content = self.__model.with_structured_output(schema = ContentSchema, method = "json_schema").invoke(self.__nodes.generate_content(state["topic"], plan, state["plan"][state["index"]], information))

        return {"content" : state["plan"][state["index"]] + "\n" + content["content"]}
    
    def __write_content(self, state: GraphSchema):
        
        content = state["content"]

        self.tools.write_in_file_tool(content)

        index = state["index"]

        return {"index" : index + 1}
    
    def __planning_check(self, state: GraphSchema) -> bool:
        if len(state["plan"]) > 0:
            return self.__model.with_structured_output(schema = BooleanSchema, method = "json_schema").invoke(self.__nodes.planning_check(state["topic"], state["output_format"], state["queries"], state["plan"]))["check"]
        else:
            return True
        
    def __information_check(self, state: GraphSchema) -> bool:
        information = ""
        for document in state["documents"]:
            information += f"\n{document.page_content}"

        need_more_documents = False

        info_check = self.__model.with_structured_output(schema = BooleanSchema, method = "json_schema").invoke(self.__nodes.information_check(state["topic"], state["output_format"], state["plan"][state["index"]], information))["check"]
        if not info_check:
            state["topic"] = state["plan"][state["index"]]
            need_more_documents = True

        state["need_more_documents"] = need_more_documents
        
        return info_check
    
    def __content_check(self, state: GraphSchema) -> bool:
        information = ""
        for document in state["documents"]:
            information += f"\n{document.page_content}"

        return self.__model.with_structured_output(schema = BooleanSchema, method = "json_schema").invoke(self.__nodes.content_check(state["topic"], state["output_format"], state["plan"][state["index"]], information, state["content"]))["check"]

    def __heading_left_check(self, state: GraphSchema) -> bool:
        return state["index"] < len(state["plan"])