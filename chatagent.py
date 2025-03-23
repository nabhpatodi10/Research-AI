import time
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, END
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import tool, BaseTool

from langchain_openai import ChatOpenAI
from openai import RateLimitError

import structures
from tools import tools
from chains import Chains

class Tools:

    __tools: tools
    __chains: Chains

    def __init__(self, session_id: str):
        self.__tools = tools(session_id)
        self.__chains = Chains(self.__tools)

    def get_previous_messages(self) -> list[AnyMessage]:
        messages = self.__tools.get_messages()
        for i in messages:
            if isinstance(i, AIMessage) and (i.content[0] == "Related Topics" or i.content[0] == "URLs" or i.content[0] == "Expert Section Content"):
                messages.remove(i)
        return messages
    
    def vector_search_tool(self, query: str) -> list[Document]:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        return self.__tools.vector_search_tool(query)
    
    def web_search_tool(self, query: str) -> list[Document]:
        """Web Search tool to access documents from the web based on the given search query"""
        __urls =  self.__chains.web_search({query: 5})
        return self.__chains.web_scrape(__urls)
    
    def return_tools(self) -> list[BaseTool]:
        return [tool(self.vector_search_tool), tool(self.web_search_tool)]

class ChatAgent:

    def __init__(self, session_id: str, model: ChatOpenAI = ChatOpenAI(model = "gpt-4o-mini")):
        
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
        self.__tool_class = Tools(session_id)
        __tool_list = self.__tool_class.return_tools()
        self.__tools = {t.name: t for t in __tool_list}
        self.__model = model.bind_tools(__tool_list)

    def __call_llm(self, state: structures.AgentState):
        try:
            if len(state["messages"]) == 2:
                messages = [state["messages"][0]] + self.__tool_class.get_previous_messages() + [state["messages"][1]]
            else:
                messages = state["messages"]
            message = self.__model.invoke(messages)
            return {"messages" : [message]}
        except RateLimitError:
            time.sleep(10)
            self.__call_llm(state)

    def __take_action(self, state: structures.AgentState):
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
                            output += f"Document {i+1}:\n{result[i].page_content}\nSource: {result[i].metadata['source']}\n\n"
                    if output == "":
                        output = "No documents found"
                    result = output
                else:
                    result = "Invalid tool output, try again"
            results.append(ToolMessage(tool_call_id = t["id"], name = t["name"], content = str(result)))
        print("Back to the model!")
        return {"messages" : results}

    def __check_action(self, state: structures.AgentState):
        return len(state["messages"][-1].tool_calls) > 0