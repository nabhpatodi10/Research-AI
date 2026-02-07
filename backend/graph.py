from dotenv import load_dotenv
load_dotenv()

from typing import List, TypedDict
import asyncio

from langchain.agents import create_agent
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
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
    perspective_content: List[List[ContentSection]]
    final_document: CompleteDocument

class ResearchGraph:
    
    def __init__(self, session_id: str, database: Database, browser: Browser):
        self.__node = Nodes()
        self.__gpt_model = ChatOpenAI(model = "gpt-5-mini", reasoning={"effort": "medium"}, verbosity="high", use_responses_api=True)
        self.__gemini_model = ChatGoogleGenerativeAI(model = "gemini-3-flash-preview", thinking_level="high")
        self.__summary_model = ChatGoogleGenerativeAI(model = "models/gemini-flash-lite-latest")
        self.__final_content_model = ChatOpenAI(model = "gpt-5.2", reasoning={"effort": "xhigh"}, verbosity="high", use_responses_api=True)
        self.__tools = Tools(session_id, database, browser).return_tools()
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

    def __extract_structured_response(self, result: dict, expected_type: type, fallback_title: str = ""):
        structured = result.get("structured_response") if isinstance(result, dict) else None
        if isinstance(structured, expected_type):
            return structured
        if expected_type is ContentSection:
            messages = result.get("messages", []) if isinstance(result, dict) else []
            last_message = messages[-1] if messages else None
            fallback_content = ""
            if last_message is not None:
                fallback_content = getattr(last_message, "text", None) or str(getattr(last_message, "content", ""))
            return ContentSection(section_title=fallback_title, content=fallback_content, citations=[])
        raise ValueError(f"Agent did not return a structured response of type {expected_type.__name__}.")

    @staticmethod
    def __message_text(message: object) -> str:
        text = getattr(message, "text", None)
        if isinstance(text, str) and text:
            return text
        return str(getattr(message, "content", ""))

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
        perspectives = await self.__gemini_model.with_structured_output(Perspectives).ainvoke(
            self.__node.generate_perspectives(state["document_outline"].as_str)
        )
        return {"perspectives": perspectives}
    
    async def __generate_content_for_perspectives(self, state: graphSchema):
        agents = []
        for index, expert in enumerate(state["perspectives"].experts):
            agent = create_agent(
                model=self.__gpt_model if index % 2 == 0 else self.__gemini_model,
                tools=self.__tools,
                system_prompt=self.__node.perspective_agent(expert, state["document_outline"].as_str),
                response_format=ContentSection
            )
            agents.append(agent)

        if len(agents) == 0:
            return {"perspective_content": []}

        summaries: list[str | None] = [None for _ in range(len(agents))]
        expert_histories: list[list[str]] = [[] for _ in range(len(agents))]
        perspective_content: list[list[ContentSection]] = []

        for section in state["document_outline"].sections:
            section_tasks = []
            for expert_index, agent in enumerate(agents):
                prompt = f"Write the content for the section:\n{section.as_str}"
                if summaries[expert_index]:
                    prompt += f"\n\nSummary of the previous sections:\n{summaries[expert_index]}"
                section_tasks.append(agent.ainvoke({"messages": [HumanMessage(content=prompt)]}))

            section_results = await asyncio.gather(*section_tasks)
            section_content: list[ContentSection] = []
            for expert_index, result in enumerate(section_results):
                content = self.__extract_structured_response(
                    result,
                    ContentSection,
                    fallback_title=section.section_title,
                )
                section_content.append(content)
                expert_histories[expert_index].append(content.as_str)

            perspective_content.append(section_content)
            summary_tasks = [
                self.__summary_model.ainvoke(
                    self.__node.generate_rolling_summary("\n\n".join(expert_histories[expert_index]))
                )
                for expert_index in range(len(agents))
            ]
            summary_messages = await asyncio.gather(*summary_tasks)
            summaries = [self.__message_text(message) for message in summary_messages]

        return {"perspective_content": perspective_content}
    
    async def __final_section_generation(self, state: graphSchema):
        final_sections: list[ContentSection] = []
        summary = None
        for section_content in state["perspective_content"]:
            if len(section_content) == 0:
                continue
            final_section = await self.__final_content_model.with_structured_output(ContentSection).ainvoke(
                self.__node.generate_combined_section(
                    "\n\n".join([content.as_str for content in section_content]),
                    state["document_outline"].as_str,
                    summary
                )
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
