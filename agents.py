from typing import TypedDict, Annotated
import operator
from langchain_core.messages import AnyMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END

class SearchAgentSchema(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]

class SearchAgent:

    def __init__(self, model, tools: list, system: str = ""):
        self.__system = system
        graph = StateGraph(SearchAgentSchema)
        graph.add_node("model", self.__call_llm)
        graph.add_node("action", self.__take_action)
        graph.add_conditional_edges(
            "model",
            self.__check_action,
            {True : "action", False : END}
        )
        graph.add_edge("action", "model")
        graph.set_entry_point("model")
        self.graph = graph.compile()
        self.__tools = {t.name: t for t in tools}
        self.__model = model.bind_tools(tools)

    def __call_llm(self, state: SearchAgentSchema):
        messages = state["messages"]
        if self.__system:
            messages = [SystemMessage(content = self.__system)] + messages
        message = self.__model.invoke(messages)
        return {"messages" : [message]}
    
    def __take_action(self, state: SearchAgentSchema):
        tool_calls = state["messages"][-1].tool_calls
        results = []
        for t in tool_calls:
            print(f"Calling: {t}")
            if not t["name"] in self.__tools:
                result = "bad tool name, retry"
                print(result)
            else:
                result = self.__tools[t["name"]].invoke(t["args"])
            results.append(ToolMessage(tool_call_id = t["id"], name = t["name"], content = str(result)))
        print("Back to the model!")
        return {"messages" : results}
    
    def __check_action(self, state: SearchAgentSchema):
        return len(state["messages"][-1].tool_calls) > 0