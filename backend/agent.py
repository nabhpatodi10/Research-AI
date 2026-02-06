import asyncio
import operator
from typing import Annotated, Any, TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, SystemMessage
from playwright.async_api import Browser

from database import Database
from tools import Tools


class AgentExecutionState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    chat_history: list[BaseMessage]


def _is_non_gpt_model(model: BaseChatModel) -> bool:
    model_attr = str(getattr(model, "model", "") or "").lower()
    model_name_attr = str(getattr(model, "model_name", "") or "").lower()
    has_model_id = bool(model_attr or model_name_attr)
    return has_model_id and ("gpt" not in model_attr) and ("gpt" not in model_name_attr)


def _strip_reasoning_blocks_if_needed(message: BaseMessage, model: BaseChatModel) -> BaseMessage:
    if not isinstance(message, AIMessage):
        return message
    if not _is_non_gpt_model(model):
        return message

    response_metadata = getattr(message, "response_metadata", None) or {}
    source_model_name = str(response_metadata.get("model_name", "") or "").lower()
    if "gpt" not in source_model_name:
        return message

    content_blocks = getattr(message, "content_blocks", None)
    if not isinstance(content_blocks, list):
        return message

    blocks = [
        block
        for block in content_blocks
        if not (isinstance(block, dict) and block.get("type") == "reasoning")
    ]
    try:
        return AIMessage(
            content=message.content,
            content_blocks=blocks,
            name=message.name,
            id=message.id,
            tool_calls=message.tool_calls,
            response_metadata=message.response_metadata,
            additional_kwargs=message.additional_kwargs,
        )
    except Exception:
        return message


async def get_chat_history(database: Database, session_id: str, model: BaseChatModel) -> list[BaseMessage]:
    previous_messages = await database.get_messages(session_id)
    chat_history: list[BaseMessage] = []
    if not previous_messages:
        return chat_history

    conversation_turns = 7
    for idx, message in enumerate(reversed(previous_messages), start=1):
        if conversation_turns <= 0:
            break

        message = _strip_reasoning_blocks_if_needed(message, model)
        if isinstance(message, HumanMessage):
            chat_history.insert(0, message)
            conversation_turns -= 1
        elif isinstance(message, (AIMessage, ToolMessage)):
            chat_history.insert(0, message)

        # Yield periodically when scanning large histories to keep loop responsive.
        if idx % 100 == 0:
            await asyncio.sleep(0)
    return chat_history


class ChatHistoryMiddleware(AgentMiddleware[AgentExecutionState, Any]):
    def __init__(self, database: Database, session_id: str, model: BaseChatModel):
        self._database = database
        self._session_id = session_id
        self._model = model

    async def abefore_agent(self, state: AgentExecutionState, runtime: Any) -> dict[str, Any]:
        chat_history = await get_chat_history(self._database, self._session_id, self._model)
        return {"chat_history": chat_history}

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        state = request.state or {}
        chat_history = state.get("chat_history", [])
        if chat_history:
            request = request.override(messages=[*chat_history, *request.messages])
        return await handler(request)


class UnknownToolFallbackMiddleware(AgentMiddleware[AgentExecutionState, Any]):
    async def awrap_tool_call(self, request: Any, handler: Any) -> ToolMessage | Any:
        if request.tool is not None:
            return await handler(request)

        tool_call = request.tool_call or {}
        tool_call_id = ""
        tool_name = None
        if isinstance(tool_call, dict):
            tool_call_id = str(tool_call.get("id", "") or "")
            tool_name = tool_call.get("name")
        else:
            tool_call_id = str(getattr(tool_call, "id", "") or "")
            tool_name = getattr(tool_call, "name", None)

        return ToolMessage(
            tool_call_id=tool_call_id,
            name=tool_name,
            content="bad tool name, retry",
        )


class PersistMessagesMiddleware(AgentMiddleware[AgentExecutionState, Any]):
    def __init__(self, database: Database, session_id: str):
        self._database = database
        self._session_id = session_id

    async def aafter_agent(self, state: AgentExecutionState, runtime: Any) -> None:
        messages = state.get("messages", [])
        if messages:
            await self._database.add_messages(self._session_id, messages)


def _normalize_system_prompt(
    system_prompt: SystemMessage | list[SystemMessage] | str | None,
) -> SystemMessage | str | None:
    if isinstance(system_prompt, list):
        if not system_prompt:
            return None
        if len(system_prompt) == 1:
            return system_prompt[0]
        return "\n\n".join(str(message.content) for message in system_prompt)
    return system_prompt


class Agent:
    def __init__(
        self,
        session_id: str,
        database: Database,
        model: BaseChatModel,
        system_prompt: SystemMessage | list[SystemMessage] | str | None,
        browser: Browser,
    ):
        tool_list = Tools(session_id, database, browser).return_tools()
        self.graph = create_agent(
            model=model,
            tools=tool_list,
            system_prompt=_normalize_system_prompt(system_prompt),
            middleware=[
                ChatHistoryMiddleware(database, session_id, model),
                UnknownToolFallbackMiddleware(),
                PersistMessagesMiddleware(database, session_id),
            ],
            state_schema=AgentExecutionState,
        )
