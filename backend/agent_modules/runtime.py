from typing import Any

from langchain.agents import create_agent
from langchain.chat_models import BaseChatModel
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Command
from playwright.async_api import Browser

from database import Database
from graph import ResearchGraph
from settings import build_langsmith_thread_config
from structures import CompleteDocument
from tools import Tools

from .helpers import extract_last_ai_message, normalize_system_prompt
from .middleware import (
    ChatHistoryMiddleware,
    PersistMessagesMiddleware,
    ResearchCommandMiddleware,
    UnknownToolFallbackMiddleware,
)
from .state import AgentExecutionState


class Agent:
    async def __run_research_graph(self, state: AgentExecutionState) -> dict[str, Any]:
        research_idea = str(state.get("research_idea", "") or "").strip()
        if not research_idea:
            no_idea_message = AIMessage(
                content="I need a specific research idea before handing off to the research workflow."
            )
            await self.__database.add_messages(self.__session_id, [no_idea_message])
            return {"messages": [no_idea_message]}

        graph_result = await self.__research_graph.graph.ainvoke(
            {"research_idea": research_idea},
            config=self.__thread_config,
        )
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
        self.__thread_config = build_langsmith_thread_config(session_id)
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
            last_ai_message = extract_last_ai_message(runtime.state.get("messages", []))
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
            system_prompt=normalize_system_prompt(system_prompt),
            middleware=[
                ResearchCommandMiddleware(
                    force_research_payload=force_research_payload if allow_research_handoff else None,
                    ask_research_topic_only=ask_research_topic_only,
                ),
                ChatHistoryMiddleware(
                    database,
                    session_id,
                    model,
                    run_config=self.__thread_config,
                ),
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
