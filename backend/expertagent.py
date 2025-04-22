import time
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, END
from langchain_core.documents import Document

from langchain_openai import ChatOpenAI
from openai import RateLimitError
import json

import structures

class ExpertAgent:

    def __init__(self, tools: list, model: ChatOpenAI = ChatOpenAI(model = "gpt-4.1-mini")):

        __graph = StateGraph(structures.AgentState)
        __graph.add_node("llm", self.__call_llm)
        __graph.add_node("action", self.__take_action)
        __graph.add_conditional_edges(
            "llm",
            self.__check_action,
            {True : "action", False : END}
        )
        __graph.add_edge("action", "llm")
        __graph.set_entry_point("llm")
        self.graph = __graph.compile()
        self.__tools = {t.name: t for t in tools}
        self.__model = model.bind_tools(tools)

    def __call_llm(self, state: structures.AgentState):
        try:
            messages = state["messages"]
            message = self.__model.invoke(messages)
            return {"messages" : [message]}
        except RateLimitError:
            time.sleep(20)
            self.__call_llm(state)
    
    def __take_action(self, state: structures.AgentState):
        try:
            tool_calls = state["messages"][-1].tool_calls
            results = []
            for t in tool_calls:
                print(f"Calling: {t}")
                if not t["name"] in self.__tools:
                    result = "bad tool name, retry"
                    print(result)
                else:
                    result = self.__tools[t["name"]].invoke(t["args"])
                    if isinstance(result, list):
                        output = ""
                        for i in range(len(result)):
                            if isinstance(result[i], Document):
                                content = json.loads(result[i].page_content)
                                output += f"Document {i+1}:\n{content["content"]}\nSource: {content["metadata"]["source"]}\n\n"
                        if output == "":
                            output = "No documents found"
                        result = output
                    else:
                        result = "Invalid tool output, try again"
                results.append(ToolMessage(tool_call_id = t["id"], name = t["name"], content = str(result)))
            print("Back to the model!")
            return {"messages" : results}
        except Exception as error:
            print(error)
            raise error
    
    def __check_action(self, state: structures.AgentState):
        return len(state["messages"][-1].tool_calls) > 0