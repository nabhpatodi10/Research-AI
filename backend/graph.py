from dotenv import load_dotenv
load_dotenv()

from time import perf_counter
from typing import List, TypedDict
import asyncio

from langchain.agents import create_agent
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from playwright.async_api import Browser

from database import Database
from nodes import Nodes
from structures import Outline, Perspectives, CompleteDocument, ContentSection
from tools import Tools

class graphSchema(TypedDict):
    research_idea: str
    document_outline: Outline
    perspectives: Perspectives
    perspective_content: List[List[str]]
    final_document: CompleteDocument

class ResearchGraph:

    @staticmethod
    def __expert_count_for_breadth(research_breadth: str) -> int:
        if research_breadth == "low":
            return 1
        if research_breadth == "high":
            return 5
        return 3
    
    def __init__(
        self,
        session_id: str,
        database: Database,
        browser: Browser,
        model_tier: str = "pro",
        research_breadth: str = "medium",
        research_depth: str = "high",
        document_length: str = "high",
    ):
        self.__node = Nodes()
        gpt_model_name = "gpt-5-nano" if model_tier == "mini" else "gpt-5-mini"
        self.__gemini_model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", thinking_level="high") if model_tier == "pro" else ChatGoogleGenerativeAI(model="models/gemini-flash-latest", thinking_budget=-1)
        verbosity = document_length if document_length in {"low", "medium", "high"} else "high"
        self.__research_breadth = research_breadth
        self.__expert_count = self.__expert_count_for_breadth(research_breadth)
        self.__gpt_model = ChatOpenAI(
            model=gpt_model_name,
            reasoning={"effort": "medium"},
            verbosity=verbosity,
            use_responses_api=True,
            service_tier="priority",
            timeout=180.0,
        )
        self.__summary_model = ChatGoogleGenerativeAI(model = "models/gemini-flash-lite-latest")
        self.__final_content_model = ChatOpenAI(
            model=gpt_model_name,
            reasoning={"effort": "high"},
            verbosity=verbosity,
            use_responses_api=True,
            service_tier="priority",
            timeout=180.0,
        )
        self.__section_attempt_timeout_seconds = 300.0
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

    def __extract_structured_response(self, result: dict, expected_type: type):
        structured = result.get("structured_response") if isinstance(result, dict) else None
        if isinstance(structured, expected_type):
            return structured
        raise ValueError(f"Agent did not return a structured response of type {expected_type.__name__}.")

    @staticmethod
    def __message_text(message: object) -> str:
        text = getattr(message, "text", None)
        if isinstance(text, str) and text:
            return text
        return str(getattr(message, "content", "")).strip()

    @staticmethod
    def __is_structured_output_error(error: Exception) -> bool:
        error_name = error.__class__.__name__
        error_text = str(error)
        return (
            error_name == "StructuredOutputValidationError"
            or "StructuredOutputValidationError" in error_text
            or "Failed to parse structured output" in error_text
        )

    async def __invoke_section_agent(
        self,
        agent: object,
        prompt: str,
    ) -> dict:
        return await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})

    @staticmethod
    def __fallback_section_text(section_title: str) -> str:
        return f"Could not generate section content for '{section_title}' due to repeated generation failures."

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
                content_text = self.__extract_agent_text_content(result).strip()
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
                    return self.__fallback_section_text(section_title)

                delay = self.__section_retry_delays[attempt - 1]
                print(
                    f"[graph] Expert '{expert_label}' attempt {attempt}/{attempt_count} "
                    f"failed for section '{section_title}': {error}. Retrying in {delay:.1f}s."
                )
                await asyncio.sleep(delay)

        return self.__fallback_section_text(section_title)

    def __extract_agent_text_content(
        self,
        result: dict,
    ) -> str:
        messages = result.get("messages", []) if isinstance(result, dict) else []
        if not messages:
            return ""

        for message in reversed(messages):
            if isinstance(message, AIMessage):
                text = self.__message_text(message)
                if text:
                    return text

        return self.__message_text(messages[-1])

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
                next_summary = self.__message_text(summary_message).strip()
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
            if not self.__is_structured_output_error(error):
                raise

        return await self.__final_content_model.with_structured_output(ContentSection).ainvoke(messages)

    async def __generate_document_outline(self, state: graphSchema):
        agent = create_agent(
            model=self.__gemini_model,
            tools=self.__tools,
            system_prompt=self.__node.generate_outline(),
            response_format=Outline
        )
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=f"Research idea:\n{state['research_idea']}")]}
        )
        document_outline: Outline = self.__extract_structured_response(result, Outline)
        return {"document_outline": document_outline}
    
    async def __generate_perspectives(self, state: graphSchema):
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
                    [self.__fallback_section_text(section.section_title) for section in sections]
                )
                continue

            normalized = list(result)
            if len(normalized) < len(sections):
                missing = len(sections) - len(normalized)
                normalized.extend(
                    [
                        self.__fallback_section_text(sections[len(normalized) + offset].section_title)
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
                row.append(text if text else self.__fallback_section_text(section.section_title))
            perspective_content.append(row)

        return {"perspective_content": perspective_content}

    def __build_low_breadth_document(self, state: graphSchema) -> CompleteDocument:
        sections = list(state["document_outline"].sections)
        perspective_rows = list(state.get("perspective_content", []))
        final_sections: list[ContentSection] = []

        for section_index, outline_section in enumerate(sections):
            section_title = str(getattr(outline_section, "section_title", f"Section {section_index + 1}") or f"Section {section_index + 1}")
            section_text = ""
            if section_index < len(perspective_rows) and perspective_rows[section_index]:
                section_text = str(perspective_rows[section_index][0] or "").strip()
            if not section_text:
                section_text = self.__fallback_section_text(section_title)

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
            summary = self.__message_text(summary_message)
        
        final_document = CompleteDocument(
            title=state["document_outline"].document_title,
            sections=final_sections
        )

        return {"final_document": final_document}
