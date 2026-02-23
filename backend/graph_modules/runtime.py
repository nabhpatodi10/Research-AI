import asyncio
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from playwright.async_api import Browser

from database import Database
from nodes import Nodes
from settings import build_langsmith_thread_config, get_settings
from tools import Tools

from .helpers import expert_count_for_breadth
from .runtime_modules.callbacks import emit_progress, emit_state_checkpoint
from .runtime_modules.node_final_sections import run_final_section_generation
from .runtime_modules.node_outline import run_generate_document_outline
from .runtime_modules.node_perspective_content import run_generate_content_for_perspectives
from .runtime_modules.node_perspectives import run_generate_perspectives
from .runtime_modules.section_generation import (
    build_low_breadth_document,
    generate_final_section,
    run_expert_pipeline,
)
from .runtime_modules.state_codec import (
    deserialize_graph_state,
    next_node_after,
    resolve_resume_node,
    serialize_graph_state,
)
from .runtime_modules.visual_repair import repair_section_visualizations, resolve_repair_task
from .schema import graphSchema
from .visual_tier2 import PlaywrightVisualTier2Validator


class ResearchGraph:
    NODE_SEQUENCE = (
        "generate_document_outline",
        "generate_perspectives",
        "generate_content_for_perspectives",
        "final_section_generation",
    )

    def __init__(
        self,
        session_id: str,
        database: Database,
        browser: Browser,
        model_tier: str = "pro",
        research_breadth: str = "medium",
        research_depth: str = "high",
        document_length: str = "high",
        progress_callback: Any = None,
    ):
        self.__node = Nodes()
        settings = get_settings()
        gpt_model_name = "gpt-5-nano" if model_tier == "mini" else "gpt-5-mini"
        self.__gemini_model = (
            ChatGoogleGenerativeAI(model="gemini-3-flash-preview", thinking_level="high")
            if model_tier == "pro"
            else ChatGoogleGenerativeAI(model="models/gemini-flash-latest", thinking_budget=-1)
        )
        verbosity = document_length if document_length in {"low", "medium", "high"} else "high"
        self.__research_breadth = research_breadth
        self.__expert_count = expert_count_for_breadth(research_breadth)
        self.__gpt_model = ChatOpenAI(
            model=gpt_model_name,
            reasoning={"effort": "medium"},
            verbosity=verbosity,
            use_responses_api=True,
            timeout=600.0,
        )
        self.__summary_model = ChatGoogleGenerativeAI(model="models/gemini-flash-lite-latest")
        self.__progress_callback = progress_callback
        self.__final_content_model = ChatOpenAI(
            model=gpt_model_name,
            reasoning={"effort": "high"},
            verbosity=verbosity,
            use_responses_api=True,
            timeout=600.0,
        )
        self.__section_attempt_timeout_seconds = 900.0
        self.__section_retry_delays = (0.5, 1.0)
        self.__visual_repair_enabled = bool(settings.visual_repair_enabled)
        self.__visual_repair_max_retries = max(0, int(settings.visual_repair_max_retries))
        self.__visual_repair_retry_timeout_seconds = max(
            1.0,
            float(settings.visual_repair_retry_timeout_seconds),
        )
        self.__visual_tier2_enabled = bool(settings.visual_tier2_enabled)
        self.__visual_tier2_fail_open = bool(settings.visual_tier2_fail_open)
        self.__visual_tier2_validator = PlaywrightVisualTier2Validator(
            settings,
            session_id=session_id,
            browser=browser,
        )
        self.__thread_config = build_langsmith_thread_config(session_id)
        self.__tools = Tools(
            session_id=session_id,
            database=database,
            browser=browser,
            research_depth=research_depth,
        ).return_tools()

        __graph = StateGraph(graphSchema)
        __graph.add_node("generate_document_outline", self.__generate_document_outline)
        __graph.add_node("generate_perspectives", self.__generate_perspectives)
        __graph.add_node("generate_content_for_perspectives", self.__generate_content_for_perspectives)
        __graph.add_node("final_section_generation", self.__final_section_generation)
        __graph.add_edge("generate_document_outline", "generate_perspectives")
        __graph.add_edge("generate_perspectives", "generate_content_for_perspectives")
        __graph.add_edge("generate_content_for_perspectives", "final_section_generation")
        __graph.add_edge("final_section_generation", END)
        __graph.set_entry_point("generate_document_outline")
        self.graph = __graph.compile()

    def deserialize_graph_state(self, graph_state: dict[str, Any] | None) -> dict[str, Any]:
        return deserialize_graph_state(graph_state)

    def serialize_graph_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return serialize_graph_state(state)

    @classmethod
    def _next_node_after(cls, node_name: str) -> str | None:
        return next_node_after(cls.NODE_SEQUENCE, node_name)

    @classmethod
    def _resolve_resume_node(
        cls,
        requested_node: str | None,
        state: dict[str, Any],
    ) -> str | None:
        return resolve_resume_node(cls.NODE_SEQUENCE, requested_node, state)

    async def __emit_progress(self, node_name: str) -> None:
        await emit_progress(self.__progress_callback, node_name)

    async def __emit_state_checkpoint(
        self,
        callback: Any,
        completed_node: str,
        state: dict[str, Any],
    ) -> None:
        await emit_state_checkpoint(
            callback,
            completed_node=completed_node,
            state=state,
            serialize_state=self.serialize_graph_state,
            next_node_after=self._next_node_after,
        )

    async def run_resumable(
        self,
        research_idea: str,
        graph_state: dict[str, Any] | None = None,
        resume_from_node: str | None = None,
        checkpoint_callback: Any = None,
    ) -> dict[str, Any]:
        initial_state = self.deserialize_graph_state(graph_state)
        initial_state["research_idea"] = str(research_idea or "").strip()

        start_node = self._resolve_resume_node(resume_from_node, initial_state)
        if start_node is None:
            return initial_state

        state: dict[str, Any] = dict(initial_state)
        run_map = {
            "generate_document_outline": self.__generate_document_outline,
            "generate_perspectives": self.__generate_perspectives,
            "generate_content_for_perspectives": self.__generate_content_for_perspectives,
            "final_section_generation": self.__final_section_generation,
        }

        should_run = False
        for node_name in self.NODE_SEQUENCE:
            if node_name == start_node:
                should_run = True
            if not should_run:
                continue

            node_fn = run_map[node_name]
            result = await node_fn(state)
            if isinstance(result, dict):
                state.update(result)
            await self.__emit_state_checkpoint(
                callback=checkpoint_callback,
                completed_node=node_name,
                state=state,
            )

        return state

    async def __run_expert_pipeline(
        self,
        expert_index: int,
        expert_name: str,
        expert_agent: object,
        sections: list,
    ) -> list[str]:
        return await run_expert_pipeline(
            expert_index=expert_index,
            expert_name=expert_name,
            expert_agent=expert_agent,
            sections=sections,
            summary_model=self.__summary_model,
            node_builder=self.__node,
            section_retry_delays=self.__section_retry_delays,
            section_attempt_timeout_seconds=self.__section_attempt_timeout_seconds,
            run_config=self.__thread_config,
        )

    async def __generate_final_section(
        self,
        section_content: list[str],
        outline_str: str,
        summary: str | None,
    ):
        return await generate_final_section(
            section_content=section_content,
            outline_str=outline_str,
            summary=summary,
            node_builder=self.__node,
            final_content_model=self.__final_content_model,
            run_config=self.__thread_config,
        )

    async def __repair_section_visualizations(self, section):
        return await repair_section_visualizations(
            section,
            visual_repair_enabled=self.__visual_repair_enabled,
            visual_repair_max_retries=self.__visual_repair_max_retries,
            visual_repair_retry_timeout_seconds=self.__visual_repair_retry_timeout_seconds,
            model=self.__final_content_model,
            node_builder=self.__node,
            tier2_validator=self.__visual_tier2_validator,
            tier2_enabled=self.__visual_tier2_enabled,
            tier2_fail_open=self.__visual_tier2_fail_open,
            run_config=self.__thread_config,
        )

    async def __resolve_repair_task(self, task, fallback_section):
        return await resolve_repair_task(
            task,
            fallback_section,
            tier2_validator=self.__visual_tier2_validator,
            tier2_enabled=self.__visual_tier2_enabled,
            tier2_fail_open=self.__visual_tier2_fail_open,
        )

    async def __generate_document_outline(self, state: graphSchema):
        return await run_generate_document_outline(
            state,
            emit_progress=self.__emit_progress,
            gemini_model=self.__gemini_model,
            tools=self.__tools,
            node_builder=self.__node,
            run_config=self.__thread_config,
        )

    async def __generate_perspectives(self, state: graphSchema):
        return await run_generate_perspectives(
            state,
            emit_progress=self.__emit_progress,
            gemini_model=self.__gemini_model,
            node_builder=self.__node,
            expert_count=self.__expert_count,
            run_config=self.__thread_config,
        )

    async def __generate_content_for_perspectives(self, state: graphSchema):
        return await run_generate_content_for_perspectives(
            state,
            emit_progress=self.__emit_progress,
            gpt_model=self.__gpt_model,
            gemini_model=self.__gemini_model,
            node_builder=self.__node,
            tools=self.__tools,
            run_expert_pipeline=self.__run_expert_pipeline,
        )

    def __build_low_breadth_document(self, state: graphSchema):
        return build_low_breadth_document(state)

    async def __final_section_generation(self, state: graphSchema):
        return await run_final_section_generation(
            state,
            emit_progress=self.__emit_progress,
            research_breadth=self.__research_breadth,
            build_low_breadth_document=self.__build_low_breadth_document,
            generate_final_section=self.__generate_final_section,
            repair_section_visualizations=self.__repair_section_visualizations,
            resolve_repair_task=self.__resolve_repair_task,
            summary_model=self.__summary_model,
            node_builder=self.__node,
            run_config=self.__thread_config,
        )
