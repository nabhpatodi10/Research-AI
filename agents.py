from typing import TypedDict, Annotated, List
import operator
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

class SearchAgentSchema(TypedDict):
    task: str
    plan: str
    search_queries: Annotated[list[AnyMessage], operator.add]
    data: Annotated[list[AnyMessage], operator.add]

class WritingAgentSchema(TypedDict):
    headings: List[str]
    content: Annotated[list[AnyMessage], operator.add]

class SearchAgent:

    def __init__(self, model, tools: list, system: str = ""):
        self.__system = system
        graph = StateGraph(SearchAgentSchema)
        graph.add_node("model", ...)
        graph.add_node("action", ...)
        graph.add_conditional_edges(
            "model",
            ...,
            {True : "action", False : END}
        )
        graph.add_edge("action", "model")
        graph.set_entry_point("model")
        self.__graph = graph.compile()
        self.__tools = {t.name: t for t in tools}
        self.__model = model.bind_tools(tools)
