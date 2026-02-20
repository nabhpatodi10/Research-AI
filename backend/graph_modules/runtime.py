import asyncio
import inspect
from time import perf_counter
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from playwright.async_api import Browser

from database import Database
from nodes import Nodes
from structures import CompleteDocument, ContentSection, Outline, Perspectives
from tools import Tools

from .helpers import (
    expert_count_for_breadth,
    extract_agent_text_content,
    extract_structured_response,
    fallback_section_text,
    is_structured_output_error,
    message_text,
)
from .schema import graphSchema


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

    @staticmethod
    def _normalize_nested_string_rows(value: Any) -> list[list[str]] | None:
        if not isinstance(value, list):
            return None
        normalized_rows: list[list[str]] = []
        for row in value:
            if not isinstance(row, list):
                return None
            normalized_rows.append([str(item or "") for item in row])
        return normalized_rows

    @staticmethod
    def _safe_outline(value: Any) -> Outline | None:
        if isinstance(value, Outline):
            return value
        if not isinstance(value, dict):
            return None
        try:
            return Outline.model_validate(value)
        except Exception:
            return None

    @staticmethod
    def _safe_perspectives(value: Any) -> Perspectives | None:
        if isinstance(value, Perspectives):
            return value
        if not isinstance(value, dict):
            return None
        try:
            return Perspectives.model_validate(value)
        except Exception:
            return None

    @staticmethod
    def _safe_document(value: Any) -> CompleteDocument | None:
        if isinstance(value, CompleteDocument):
            return value
        if not isinstance(value, dict):
            return None
        try:
            return CompleteDocument.model_validate(value)
        except Exception:
            return None

    def deserialize_graph_state(self, graph_state: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(graph_state, dict):
            return {}

        next_state: dict[str, Any] = {}
        research_idea = str(graph_state.get("research_idea") or "").strip()
        if research_idea:
            next_state["research_idea"] = research_idea

        outline = self._safe_outline(
            graph_state.get("document_outline") or graph_state.get("documentOutline")
        )
        if outline is not None:
            next_state["document_outline"] = outline

        perspectives = self._safe_perspectives(graph_state.get("perspectives"))
        if perspectives is not None:
            next_state["perspectives"] = perspectives

        perspective_content = self._normalize_nested_string_rows(graph_state.get("perspective_content"))
        if perspective_content is None:
            perspective_content = self._normalize_nested_string_rows(
                graph_state.get("perspectiveContent")
            )
        if perspective_content is not None:
            next_state["perspective_content"] = perspective_content

        final_document = self._safe_document(
            graph_state.get("final_document") or graph_state.get("finalDocument")
        )
        if final_document is not None:
            next_state["final_document"] = final_document

        return next_state

    def serialize_graph_state(self, state: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "research_idea": str(state.get("research_idea") or "").strip(),
        }
        outline = self._safe_outline(state.get("document_outline"))
        if outline is not None:
            payload["document_outline"] = outline.model_dump(mode="json")

        perspectives = self._safe_perspectives(state.get("perspectives"))
        if perspectives is not None:
            payload["perspectives"] = perspectives.model_dump(mode="json")

        perspective_content = self._normalize_nested_string_rows(state.get("perspective_content"))
        if perspective_content is not None:
            payload["perspective_content"] = perspective_content

        final_document = self._safe_document(state.get("final_document"))
        if final_document is not None:
            payload["final_document"] = final_document.model_dump(mode="json")

        return payload

    @classmethod
    def _next_node_after(cls, node_name: str) -> str | None:
        normalized = str(node_name or "").strip()
        if normalized not in cls.NODE_SEQUENCE:
            return None
        index = cls.NODE_SEQUENCE.index(normalized)
        if index >= len(cls.NODE_SEQUENCE) - 1:
            return None
        return cls.NODE_SEQUENCE[index + 1]

    @classmethod
    def _default_resume_node_for_state(cls, state: dict[str, Any]) -> str | None:
        if not state.get("document_outline"):
            return "generate_document_outline"
        if not state.get("perspectives"):
            return "generate_perspectives"
        if not state.get("perspective_content"):
            return "generate_content_for_perspectives"
        if not state.get("final_document"):
            return "final_section_generation"
        return None

    @classmethod
    def _resolve_resume_node(
        cls,
        requested_node: str | None,
        state: dict[str, Any],
    ) -> str | None:
        normalized = str(requested_node or "").strip()
        if not normalized:
            return cls._default_resume_node_for_state(state)
        if normalized not in cls.NODE_SEQUENCE:
            return cls._default_resume_node_for_state(state)

        if normalized == "generate_document_outline":
            return normalized
        if normalized == "generate_perspectives":
            if not state.get("document_outline"):
                return "generate_document_outline"
            return normalized
        if normalized == "generate_content_for_perspectives":
            if not state.get("document_outline"):
                return "generate_document_outline"
            if not state.get("perspectives"):
                return "generate_perspectives"
            return normalized
        if normalized == "final_section_generation":
            if not state.get("document_outline"):
                return "generate_document_outline"
            if not state.get("perspectives"):
                return "generate_perspectives"
            if not state.get("perspective_content"):
                return "generate_content_for_perspectives"
            return normalized
        return cls._default_resume_node_for_state(state)

    async def __emit_progress(self, node_name: str) -> None:
        callback = self.__progress_callback
        if callback is None:
            return
        try:
            maybe_result = callback(node_name)
            if inspect.isawaitable(maybe_result):
                await maybe_result
        except asyncio.CancelledError:
            raise
        except Exception:
            # Progress events must never break the research pipeline.
            return

    async def __emit_state_checkpoint(
        self,
        callback: Any,
        completed_node: str,
        state: dict[str, Any],
    ) -> None:
        if callback is None:
            return
        try:
            maybe_result = callback(
                completed_node,
                self.serialize_graph_state(state),
                self._next_node_after(completed_node),
            )
            if inspect.isawaitable(maybe_result):
                await maybe_result
        except asyncio.CancelledError:
            raise
        except Exception:
            # Checkpoint events must never break the research pipeline.
            return

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
            result = await node_fn(state)  # each node handles its own progress callback
            if isinstance(result, dict):
                state.update(result)
            await self.__emit_state_checkpoint(
                callback=checkpoint_callback,
                completed_node=node_name,
                state=state,
            )

        return state

    async def __invoke_section_agent(
        self,
        agent: object,
        prompt: str,
    ) -> dict:
        return await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})

    async def __invoke_section_with_retry(
        self,
        agent: object,
        prompt: str,
        section_title: str,
        expert_label: str,
    ) -> str:
        attempt_count = len(self.__section_retry_delays) + 1
        for attempt in range(1, attempt_count + 1):
            try:
                result = await asyncio.wait_for(
                    self.__invoke_section_agent(agent=agent, prompt=prompt),
                    timeout=self.__section_attempt_timeout_seconds,
                )
                content_text = extract_agent_text_content(result).strip()
                if content_text:
                    return content_text
                raise ValueError("Generated section content was empty.")
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if attempt >= attempt_count:
                    print(
                        f"[graph] Expert '{expert_label}' failed for section '{section_title}' "
                        f"after {attempt_count} attempts: {error}. Using fallback content."
                    )
                    return fallback_section_text(section_title)

                delay = self.__section_retry_delays[attempt - 1]
                print(
                    f"[graph] Expert '{expert_label}' attempt {attempt}/{attempt_count} "
                    f"failed for section '{section_title}': {error}. Retrying in {delay:.1f}s."
                )
                await asyncio.sleep(delay)

        return fallback_section_text(section_title)

    async def __run_expert_pipeline(
        self,
        expert_index: int,
        expert_name: str,
        expert_agent: object,
        sections: list,
    ) -> list[str]:
        start_time = perf_counter()
        print(f"[graph] Expert pipeline started: index={expert_index}, name='{expert_name}'")

        pipeline_outputs: list[str] = []
        expert_history: list[str] = []
        summary: str | None = None

        for section in sections:
            section_title = str(getattr(section, "section_title", "Untitled Section") or "Untitled Section")
            prompt = f"Write the content for the section:\n{section.as_str}"
            if summary:
                prompt += f"\n\nSummary of the previous sections:\n{summary}"

            section_text = await self.__invoke_section_with_retry(
                agent=expert_agent,
                prompt=prompt,
                section_title=section_title,
                expert_label=expert_name,
            )
            pipeline_outputs.append(section_text)
            expert_history.append(f"## {section_title}\n\n{section_text}".strip())

            try:
                summary_message = await self.__summary_model.ainvoke(
                    self.__node.generate_rolling_summary("\n\n".join(expert_history))
                )
                next_summary = message_text(summary_message).strip()
                if next_summary:
                    summary = next_summary
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(
                    f"[graph] Summary update failed for expert '{expert_name}' "
                    f"after section '{section_title}': {error}. Continuing without summary update."
                )

        elapsed = perf_counter() - start_time
        print(
            f"[graph] Expert pipeline completed: index={expert_index}, "
            f"name='{expert_name}', sections={len(pipeline_outputs)}, elapsed={elapsed:.2f}s"
        )
        return pipeline_outputs

    async def __generate_final_section(
        self,
        section_content: list[str],
        outline_str: str,
        summary: str | None,
    ) -> ContentSection:
        messages = self.__node.generate_combined_section(
            "\n\n".join(section_content),
            outline_str,
            summary,
        )

        try:
            return await self.__final_content_model.with_structured_output(ContentSection).ainvoke(messages)
        except Exception as error:
            if not is_structured_output_error(error):
                raise

        return await self.__final_content_model.with_structured_output(ContentSection).ainvoke(messages)

    async def __generate_document_outline(self, state: graphSchema):
        await self.__emit_progress("generate_document_outline")
        agent = create_agent(
            model=self.__gemini_model,
            tools=self.__tools,
            system_prompt=self.__node.generate_outline(),
            response_format=Outline,
        )
        result = await agent.ainvoke(
            {"messages": [self.__node.outline_research_idea_message(state["research_idea"])]}
        )
        document_outline: Outline = extract_structured_response(result, Outline)
        return {"document_outline": document_outline}

    async def __generate_perspectives(self, state: graphSchema):
        await self.__emit_progress("generate_perspectives")
        perspectives: Perspectives = await self.__gemini_model.with_structured_output(Perspectives).ainvoke(
            self.__node.generate_perspectives(
                state["document_outline"].as_str,
                count=self.__expert_count,
            )
        )
        if len(perspectives.experts) > self.__expert_count:
            perspectives = Perspectives(experts=perspectives.experts[: self.__expert_count])
        return {"perspectives": perspectives}

    async def __generate_content_for_perspectives(self, state: graphSchema):
        await self.__emit_progress("generate_content_for_perspectives")
        sections = list(state["document_outline"].sections)
        if len(sections) == 0:
            return {"perspective_content": []}

        expert_agents: list[tuple[int, str, object]] = []
        for index, expert in enumerate(state["perspectives"].experts):
            model = self.__gpt_model if index % 2 == 0 else self.__gemini_model
            system_prompt = self.__node.perspective_agent(expert, state["document_outline"].as_str)
            expert_agent = create_agent(
                model=model,
                tools=self.__tools,
                system_prompt=system_prompt,
            )
            expert_name = str(getattr(expert, "name", f"Expert {index + 1}") or f"Expert {index + 1}")
            expert_agents.append((index, expert_name, expert_agent))

        if len(expert_agents) == 0:
            return {"perspective_content": []}

        expert_tasks = [
            asyncio.create_task(
                self.__run_expert_pipeline(
                    expert_index=expert_index,
                    expert_name=expert_name,
                    expert_agent=expert_agent,
                    sections=sections,
                )
            )
            for expert_index, expert_name, expert_agent in expert_agents
        ]

        pipeline_results = await asyncio.gather(*expert_tasks, return_exceptions=True)

        expert_outputs: list[list[str]] = []
        for result_index, result in enumerate(pipeline_results):
            if isinstance(result, Exception):
                failing_expert = expert_agents[result_index][1]
                print(
                    f"[graph] Expert pipeline '{failing_expert}' crashed with: {result}. "
                    "Using fallback content for all sections."
                )
                expert_outputs.append(
                    [fallback_section_text(section.section_title) for section in sections]
                )
                continue

            normalized = list(result)
            if len(normalized) < len(sections):
                missing = len(sections) - len(normalized)
                normalized.extend(
                    [
                        fallback_section_text(sections[len(normalized) + offset].section_title)
                        for offset in range(missing)
                    ]
                )
            elif len(normalized) > len(sections):
                normalized = normalized[: len(sections)]

            expert_outputs.append(normalized)

        perspective_content: list[list[str]] = []
        for section_index, section in enumerate(sections):
            row: list[str] = []
            for expert_index in range(len(expert_outputs)):
                value = expert_outputs[expert_index][section_index]
                text = str(value or "").strip()
                row.append(text if text else fallback_section_text(section.section_title))
            perspective_content.append(row)

        return {"perspective_content": perspective_content}

    def __build_low_breadth_document(self, state: graphSchema) -> CompleteDocument:
        sections = list(state["document_outline"].sections)
        perspective_rows = list(state.get("perspective_content", []))
        final_sections: list[ContentSection] = []

        for section_index, outline_section in enumerate(sections):
            section_title = str(
                getattr(outline_section, "section_title", f"Section {section_index + 1}")
                or f"Section {section_index + 1}"
            )
            section_text = ""
            if section_index < len(perspective_rows) and perspective_rows[section_index]:
                section_text = str(perspective_rows[section_index][0] or "").strip()
            if not section_text:
                section_text = fallback_section_text(section_title)

            final_sections.append(
                ContentSection(
                    section_title=section_title,
                    content=section_text,
                    citations=[],
                )
            )

        return CompleteDocument(
            title=state["document_outline"].document_title,
            sections=final_sections,
        )

    async def __final_section_generation(self, state: graphSchema):
        await self.__emit_progress("final_section_generation")
        if self.__research_breadth == "low":
            return {"final_document": self.__build_low_breadth_document(state)}

        final_sections: list[ContentSection] = []
        summary = None
        for section_content in state["perspective_content"]:
            if len(section_content) == 0:
                continue
            final_section = await self.__generate_final_section(
                section_content=section_content,
                outline_str=state["document_outline"].as_str,
                summary=summary,
            )
            final_sections.append(final_section)
            summary_message = await self.__summary_model.ainvoke(
                self.__node.generate_rolling_summary("\n".join([section.as_str for section in final_sections]))
            )
            summary = message_text(summary_message)

        final_document = CompleteDocument(
            title=state["document_outline"].document_title,
            sections=final_sections,
        )

        return {"final_document": final_document}
