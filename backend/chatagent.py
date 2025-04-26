from dotenv import load_dotenv
load_dotenv()

import time
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, END
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.tools import tool

from langchain_openai import ChatOpenAI
from openai import RateLimitError
from playwright.async_api import Browser
import json

import structures
from database import Database
from chains import Chains

class ChatAgent:

    async def __web_search_tool(self, query: str) -> list[Document]:
        """Web Search tool to access documents from the web based on the given search query"""
        self.__chains = Chains(self.__database, self.__browser)
        __urls =  self.__chains.web_search({query: 10})
        return await self.__chains.web_scrape(__urls)

    def __init__(self, session_id: str, system_message: list[SystemMessage], browser: Browser, model: ChatOpenAI = ChatOpenAI(model = "gpt-4.1-mini")):
        self.__browser = browser
        self.__system_message = system_message
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
        self.__database = Database(session_id)
        __tool_list = self.__database.return_tool() + [tool(self.__web_search_tool)]
        self.__tools = {t.name: t for t in __tool_list}
        self.__model = model.bind_tools(__tool_list)

    def __call_llm(self, state: structures.AgentState):
        try:
            if len(state["messages"]) <= 2:
                previous_messages = self.__database.get_messages()
                for i in range(len(previous_messages)-1, -1, -1):
                    if previous_messages[i].content[0] in ["URLs", "Document Outline", "Perspectives", "Expert Section Content"]:
                        previous_messages.pop(i)
                    else:
                        content = previous_messages[i].content
                        if isinstance(content, list):
                            if content[0] == "User Input":
                                if isinstance(content[1], dict):
                                    previous_messages[i].content = f"Topic: {content[1]['topic']}\n\nOutput Format: {content[1]['output_format']}"
                                elif isinstance(content[1], str):
                                    previous_messages[i].content = content[1]
                            elif content[0] == "Related Topics":
                                previous_messages[i].content = f"Topics Searched During Research: {content[1]}"
                            elif content[0] == "Final Document":
                                previous_messages[i].content = f"Generated Document after Research (in markdown format):\n\n{content[1]}"
                            elif content[0] == "Chat":
                                previous_messages[i].content = content[1]
                state["messages"] = previous_messages + state["messages"]
                self.__database.add_human_message(HumanMessage(content=["User Input", state["messages"][-1].content]))
            messages = self.__system_message + state["messages"]
            message = self.__model.invoke(messages)
            return {"messages" : [message]}
        except RateLimitError:
            time.sleep(20)
            self.__call_llm(state)
        except Exception:
            time.sleep(40)
            self.__call_llm(state)

    async def __take_action(self, state: structures.AgentState):
        tool_calls = state["messages"][-1].tool_calls
        results = []
        for t in tool_calls:
            print(f"Calling: {t}")
            if not t["name"] in self.__tools:
                result = "bad tool name, retry"
                print(result)
            else:
                if t["name"] == "__web_search_tool":
                    result = await self.__tools[t["name"]].ainvoke(t["args"])
                elif t["name"] == "vector_search_tool":
                    result = self.__tools[t["name"]].invoke(t["args"])
                if isinstance(result, list):
                    output = ""
                    for i in range(len(result)):
                        if isinstance(result[i], Document):
                            try:
                                content = json.loads(result[i].page_content)
                                output += f"Document {i+1}:\n{content["content"]}\nSource: {content["metadata"]["source"]}\n\n"
                            except:
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
        if len(state["messages"][-1].tool_calls) > 0:
            return True
        else:
            self.__database.add_ai_message(AIMessage(content=["Chat", state["messages"][-1].content]))
            return False