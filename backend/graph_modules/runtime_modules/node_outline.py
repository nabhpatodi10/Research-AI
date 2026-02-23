from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from structures import Outline

from ..helpers import extract_structured_response


async def run_generate_document_outline(
    state: dict[str, Any],
    *,
    emit_progress: Any,
    gemini_model: Any,
    tools: list[Any],
    node_builder: Any,
    run_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await emit_progress("generate_document_outline")
    agent = create_agent(
        model=gemini_model,
        tools=tools,
        system_prompt=node_builder.generate_outline(),
        response_format=Outline,
    )
    result = await agent.ainvoke(
        {"messages": [node_builder.outline_research_idea_message(state["research_idea"])]},
        config=run_config,
    )
    document_outline: Outline = extract_structured_response(result, Outline)
    return {"document_outline": document_outline}
