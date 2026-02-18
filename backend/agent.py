import asyncio
import operator
from typing import Annotated, Any, NotRequired, TypedDict
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.chat_models import BaseChatModel
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Command
from playwright.async_api import Browser

from database import Database
from graph import ResearchGraph
from structures import CompleteDocument
from tools import Tools
from nodes import Nodes

class AgentExecutionState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    chat_history: NotRequired[list[BaseMessage]]
    research_idea: NotRequired[str]
    final_document: NotRequired[str]


def _message_text(message: BaseMessage) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def _message_role(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "User"
    if isinstance(message, AIMessage):
        return "Assistant"
    if isinstance(message, ToolMessage):
        tool_name = message.name or "tool"
        return f"Tool({tool_name})"
    return message.__class__.__name__


async def _summarize_older_messages(messages: list[BaseMessage], model: BaseChatModel) -> AIMessage | None:
    if not messages:
        return None

    max_chars = 48000
    transcript_lines: list[str] = []
    used_chars = 0
    for message in messages:
        text = _message_text(message)
        if not text:
            continue
        line = f"{_message_role(message)}: {text}"
        if used_chars + len(line) > max_chars:
            break
        transcript_lines.append(line)
        used_chars += len(line)

    if not transcript_lines:
        return None

    try:
        summary_response = await model.ainvoke(Nodes().generate_conversation_summary(transcript_lines))
        summary_text = _message_text(summary_response)
    except Exception:
        summary_text = "\n".join(transcript_lines[-12:])

    if not summary_text:
        return None

    return AIMessage(content=f"Summary of earlier conversation before latest 5 turns:\n{summary_text}")


async def get_chat_history(database: Database, session_id: str, model: BaseChatModel) -> list[BaseMessage]:
    previous_messages = await database.get_messages(session_id)
    recent_history: list[BaseMessage] = []
    older_history: list[BaseMessage] = []
    if not previous_messages:
        return recent_history

    conversation_turns = 5
    for idx, message in enumerate(reversed(previous_messages), start=1):
        if not isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
            continue

        if conversation_turns > 0:
            recent_history.insert(0, message)
            if isinstance(message, HumanMessage):
                conversation_turns -= 1
        else:
            older_history.insert(0, message)

        # Yield periodically when scanning large histories to keep loop responsive.
        if idx % 100 == 0:
            await asyncio.sleep(0)

    summary_message = await _summarize_older_messages(older_history, model)
    if summary_message is not None:
        return [summary_message, *recent_history]
    return recent_history


async def build_research_handoff_context(
    database: Database,
    session_id: str,
    model: BaseChatModel,
    additional_user_context: str | None = None,
) -> str:
    history = await get_chat_history(database, session_id, model)
    transcript_lines: list[str] = []
    for message in history:
        if not isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
            continue
        text = _message_text(message)
        if not text:
            continue
        transcript_lines.append(f"{_message_role(message)}: {text}")

    latest_context = str(additional_user_context or "").strip()
    if latest_context:
        transcript_lines.append(f"Latest user context: {latest_context}")

    if not transcript_lines:
        return latest_context

    summarize_prompt: list[BaseMessage] = [
        SystemMessage(
            content=(
                "Create a concise research handoff brief from this conversation. "
                "Capture: research idea, document requirements/output format, constraints, and important specifics. "
                "If any category is missing, say 'Not specified'."
            )
        ),
        HumanMessage(content="Conversation:\n\n" + "\n\n".join(transcript_lines)),
    ]
    try:
        summary_response = await model.ainvoke(summarize_prompt)
        summary_text = _message_text(summary_response).strip()
        if summary_text:
            return summary_text
    except Exception:
        pass

    fallback = "\n\n".join(transcript_lines[-12:]).strip()
    return fallback or latest_context


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
            latest_history_message = chat_history[-1]
            first_runtime_human = next(
                (message for message in request.messages if isinstance(message, HumanMessage)),
                None,
            )
            if (
                isinstance(latest_history_message, HumanMessage)
                and isinstance(first_runtime_human, HumanMessage)
                and _message_text(latest_history_message) == _message_text(first_runtime_human)
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

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        if self._ask_research_topic_only:
            ask_instruction = SystemMessage(
                content=(
                    "The user requested deep research but did not provide a topic. "
                    "Ask one concise follow-up question requesting the topic/idea and any output requirements. "
                    "Do not call tools."
                )
            )
            response = await handler(request.override(messages=[ask_instruction, *request.messages]))
            if isinstance(response, AIMessage):
                if getattr(response, "tool_calls", None):
                    return AIMessage(
                        content=(
                            "Sure. What topic or idea should I research, and are there any specific "
                            "requirements for the final document?"
                        )
                    )
                if _message_text(response):
                    return response
            return AIMessage(
                content=(
                    "Sure. What topic or idea should I research, and are there any specific "
                    "requirements for the final document?"
                )
            )

        if not self._force_research_payload:
            return await handler(request)

        force_instruction = SystemMessage(
            content=(
                "You must call the tool `handoff_to_research_graph` exactly once using the provided research context. "
                "Do not answer directly before calling the tool."
            )
        )
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


def _extract_last_ai_message(messages: list[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


class Agent:
    async def __run_research_graph(self, state: AgentExecutionState) -> dict[str, Any]:
        research_idea = str(state.get("research_idea", "") or "").strip()
        if not research_idea:
            no_idea_message = AIMessage(
                content="I need a specific research idea before handing off to the research workflow."
            )
            await self.__database.add_messages(self.__session_id, [no_idea_message])
            return {"messages": [no_idea_message]}

        graph_result = await self.__research_graph.graph.ainvoke({"research_idea": research_idea})
        final_document = graph_result.get("final_document")

        if isinstance(final_document, CompleteDocument):
            final_document_text = final_document.as_str
        elif final_document is None:
            final_document_text = "The research workflow completed, but no final document was returned."
        else:
            final_document_text = str(final_document)

        final_message = AIMessage(content=final_document_text)
        await self.__database.add_messages(self.__session_id, [final_message])
        return {"final_document": final_document_text, "messages": [final_message]}

    def __init__(
        self,
        session_id: str,
        database: Database,
        model: BaseChatModel,
        system_prompt: SystemMessage | list[SystemMessage] | str | None,
        browser: Browser,
        model_tier: str = "pro",
        research_breadth: str = "medium",
        research_depth: str = "high",
        document_length: str = "high",
        force_research_payload: str | None = None,
        ask_research_topic_only: bool = False,
        allow_research_handoff: bool = True,
    ):
        self.__session_id = session_id
        self.__database = database
        self.__research_graph = ResearchGraph(
            session_id=session_id,
            database=database,
            browser=browser,
            model_tier=model_tier,
            research_breadth=research_breadth,
            research_depth=research_depth,
            document_length=document_length,
        )

        @tool
        def handoff_to_research_graph(
            research_idea: str,
            runtime: ToolRuntime[None, AgentExecutionState],
        ) -> Command:
            """Handoff to the research graph to generate a full research document for the provided research idea."""
            idea = str(research_idea or "").strip()
            last_ai_message = _extract_last_ai_message(runtime.state.get("messages", []))
            tool_response = ToolMessage(
                content=f"Handoff initiated to research graph for research idea: {idea}",
                tool_call_id=runtime.tool_call_id or "handoff_to_research_graph",
            )
            transfer_messages: list[BaseMessage] = [tool_response]
            if last_ai_message is not None:
                transfer_messages = [last_ai_message, tool_response]

            return Command(
                goto="research_graph",
                graph=Command.PARENT,
                update={
                    "research_idea": idea,
                    "messages": transfer_messages,
                },
            )

        tool_list = Tools(
            session_id=session_id,
            database=database,
            browser=browser,
            research_depth=research_depth,
        ).return_tools()
        if allow_research_handoff:
            tool_list = [*tool_list, handoff_to_research_graph]
        chat_agent = create_agent(
            model=model,
            tools=tool_list,
            system_prompt=_normalize_system_prompt(system_prompt),
            middleware=[
                ResearchCommandMiddleware(
                    force_research_payload=force_research_payload if allow_research_handoff else None,
                    ask_research_topic_only=ask_research_topic_only,
                ),
                ChatHistoryMiddleware(database, session_id, model),
                UnknownToolFallbackMiddleware(),
                PersistMessagesMiddleware(database, session_id),
            ],
            state_schema=AgentExecutionState,
        )

        orchestrator = StateGraph(AgentExecutionState)
        orchestrator.add_node("chat_agent", chat_agent)
        orchestrator.add_node("research_graph", self.__run_research_graph)
        orchestrator.add_edge("chat_agent", END)
        orchestrator.add_edge("research_graph", END)
        orchestrator.set_entry_point("chat_agent")
        self.graph = orchestrator.compile()
