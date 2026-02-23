from __future__ import annotations

from typing import Any

from structures import Perspectives


async def run_generate_perspectives(
    state: dict[str, Any],
    *,
    emit_progress: Any,
    gemini_model: Any,
    node_builder: Any,
    expert_count: int,
    run_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await emit_progress("generate_perspectives")
    perspectives: Perspectives = await gemini_model.with_structured_output(Perspectives).ainvoke(
        node_builder.generate_perspectives(
            state["document_outline"].as_str,
            count=expert_count,
        ),
        config=run_config,
    )
    if len(perspectives.experts) > expert_count:
        perspectives = Perspectives(experts=perspectives.experts[:expert_count])
    return {"perspectives": perspectives}
