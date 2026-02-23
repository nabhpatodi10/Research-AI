from typing import Any
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware
from langchain.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from database import Database
from nodes import Nodes

from .helpers import message_text
from .history import get_chat_history
from .state import AgentExecutionState


class ChatHistoryMiddleware(AgentMiddleware[AgentExecutionState, Any]):
    def __init__(
        self,
        database: Database,
        session_id: str,
        model: BaseChatModel,
        run_config: dict[str, Any] | None = None,
    ):
        self._database = database
        self._session_id = session_id
        self._model = model
        self._run_config = dict(run_config or {})

    async def abefore_agent(self, state: AgentExecutionState, runtime: Any) -> dict[str, Any]:
        chat_history = await get_chat_history(
            self._database,
            self._session_id,
            self._model,
            run_config=self._run_config,
        )
        return {"chat_history": chat_history}

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        state = request.state or {}
        chat_history = state.get("chat_history", [])
        if chat_history:
            latest_history_message = chat_history[-1]
            first_runtime_human = next(
                (message for message in request.messages if isinstance(message, HumanMessage)),
                None,
            )
            if (
                isinstance(latest_history_message, HumanMessage)
                and isinstance(first_runtime_human, HumanMessage)
                and message_text(latest_history_message) == message_text(first_runtime_human)
            ):
                chat_history = chat_history[:-1]

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


class ResearchCommandMiddleware(AgentMiddleware[AgentExecutionState, Any]):
    def __init__(
        self,
        force_research_payload: str | None = None,
        ask_research_topic_only: bool = False,
    ):
        self._force_research_payload = str(force_research_payload or "").strip()
        self._ask_research_topic_only = bool(ask_research_topic_only)
        self._nodes = Nodes()

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        if self._ask_research_topic_only:
            ask_instruction = self._nodes.research_topic_followup_instruction()
            response = await handler(request.override(messages=[ask_instruction, *request.messages]))
            if isinstance(response, AIMessage):
                if getattr(response, "tool_calls", None):
                    return AIMessage(
                        content=(
                            "Sure. What topic or idea should I research, and are there any specific "
                            "requirements for the final document?"
                        )
                    )
                if message_text(response):
                    return response
            return AIMessage(
                content=(
                    "Sure. What topic or idea should I research, and are there any specific "
                    "requirements for the final document?"
                )
            )

        if not self._force_research_payload:
            return await handler(request)

        force_instruction = self._nodes.force_research_handoff_instruction()
        forced_request = request.override(
            messages=[force_instruction, HumanMessage(content=self._force_research_payload)]
        )
        response = await handler(forced_request)

        if isinstance(response, AIMessage):
            tool_calls = getattr(response, "tool_calls", None) or []
            for tool_call in tool_calls:
                if isinstance(tool_call, dict) and tool_call.get("name") == "handoff_to_research_graph":
                    return response

        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "handoff_to_research_graph",
                    "args": {"research_idea": self._force_research_payload},
                    "id": f"force_handoff_{uuid4().hex}",
                    "type": "tool_call",
                }
            ],
        )


class PersistMessagesMiddleware(AgentMiddleware[AgentExecutionState, Any]):
    def __init__(self, database: Database, session_id: str):
        self._database = database
        self._session_id = session_id

    async def aafter_agent(self, state: AgentExecutionState, runtime: Any) -> None:
        messages = state.get("messages", [])
        if not messages:
            return

        persistable_messages = [
            message for message in messages if not isinstance(message, HumanMessage)
        ]
        if persistable_messages:
            await self._database.add_messages(self._session_id, persistable_messages)
