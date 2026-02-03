import asyncio
from langchain_core.messages import ToolMessage, SystemMessage, AIMessage, HumanMessage, BaseMessage
from langgraph.graph import StateGraph, END
from langchain.chat_models import BaseChatModel

from structures import agent_type, AgentState
from database import Database
from tools import Tools

async def get_chat_history(database: Database, session_id: str, model: BaseChatModel) -> list[BaseMessage]:
    previous_messages = await database.get_messages(session_id)
    chat_history = []
    if len(previous_messages) > 0:
        conversation_turns = 7
        for i in previous_messages[-1::-1]:
            if conversation_turns <= 0:
                break
            if ((hasattr(model, "model") and "gpt" not in model.model) or (hasattr(model, "model_name") and "gpt" not in model.model_name)) and isinstance(i, AIMessage):
                if i.response_metadata is not None and "gpt" in i.response_metadata.get("model_name", ""):
                    blocks = [block for block in i.content_blocks if block["type"] != "reasoning"]
                    new_message = AIMessage(content=i.content, content_blocks=blocks, name=i.name, id=i.id, tool_calls=i.tool_calls, response_metadata=i.response_metadata, additional_kwargs=i.additional_kwargs)
                    i = new_message
            if isinstance(i, HumanMessage):
                chat_history.insert(0, i)
                conversation_turns -= 1
            elif isinstance(i, AIMessage) or (isinstance(i, ToolMessage)):
                chat_history.insert(0, i)
    return chat_history

class Agent:

    def __init__(
        self,
        session_id: str,
        database: Database,
        model: BaseChatModel,
        agent_type: agent_type,
        browser
    ):
        self.__system_prompt = None
        __graph = StateGraph(AgentState)
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
        self.__database = database
        tool_list = Tools(session_id, database, browser).return_tools()
        self.__tools = {t.name: t for t in tool_list}
        self.__model = model.bind_tools(tool_list)
        self.__agent_type = agent_type
        self.__session_id = session_id
        self.__old_messages = []

    async def __call_llm(self, state: AgentState):
        try:
            if len(state["messages"]) <= 1 and self.__agent_type == "chat_agent":
                self.__system_prompt = [SystemMessage(content="")]
                self.__old_messages = await get_chat_history(self.__database, self.__session_id, self.__model)
            messages = self.__system_prompt + self.__old_messages + state["messages"] if self.__agent_type == "chat_agent" else self.__system_prompt + state["messages"]
            message = await self.__model.ainvoke(messages)
            message.name = self.__agent_type
            return {"messages" : [message]}
        except Exception as e:
            print(e)
            raise e

    async def __take_action(self, state: AgentState):
        tool_calls = state["messages"][-1].tool_calls
        results: list[ToolMessage] = []
        __chains = []
        for t in tool_calls:
            print(f"Calling: {t}")
            result = "No output from the tool."
            if not t["name"] in self.__tools:
                result = "bad tool name, retry"
            else:
                __chains.append(self.__tools[t["name"]].ainvoke(t["args"]))
            tool_message = ToolMessage(tool_call_id = t["id"], name = t["name"], content = str(result))
            results.append(tool_message)
        __outputs = await asyncio.gather(*__chains)
        output_index = 0
        for tool_message in results:
            if tool_message.content == "No output from the tool." and output_index < len(__outputs):
                tool_message.content = str(__outputs[output_index])
                output_index += 1
        print("Back to the model!")
        return {"messages" : results}

    async def __check_action(self, state: AgentState):
        tool_calls = getattr(state["messages"][-1], "tool_calls", None) or []
        if len(tool_calls) > 0:
            return True
        else:
            if self.__agent_type == "chat_agent":
                await self.__database.add_messages(self.__session_id, state["messages"])
            return False