from __future__ import annotations

from typing import Any

from structures import CompleteDocument, Outline, Perspectives


def normalize_nested_string_rows(value: Any) -> list[list[str]] | None:
    if not isinstance(value, list):
        return None
    normalized_rows: list[list[str]] = []
    for row in value:
        if not isinstance(row, list):
            return None
        normalized_rows.append([str(item or "") for item in row])
    return normalized_rows


def safe_outline(value: Any) -> Outline | None:
    if isinstance(value, Outline):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return Outline.model_validate(value)
    except Exception:
        return None


def safe_perspectives(value: Any) -> Perspectives | None:
    if isinstance(value, Perspectives):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return Perspectives.model_validate(value)
    except Exception:
        return None


def safe_document(value: Any) -> CompleteDocument | None:
    if isinstance(value, CompleteDocument):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return CompleteDocument.model_validate(value)
    except Exception:
        return None


def deserialize_graph_state(graph_state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(graph_state, dict):
        return {}

    next_state: dict[str, Any] = {}
    research_idea = str(graph_state.get("research_idea") or "").strip()
    if research_idea:
        next_state["research_idea"] = research_idea

    outline = safe_outline(graph_state.get("document_outline") or graph_state.get("documentOutline"))
    if outline is not None:
        next_state["document_outline"] = outline

    perspectives = safe_perspectives(graph_state.get("perspectives"))
    if perspectives is not None:
        next_state["perspectives"] = perspectives

    perspective_content = normalize_nested_string_rows(graph_state.get("perspective_content"))
    if perspective_content is None:
        perspective_content = normalize_nested_string_rows(graph_state.get("perspectiveContent"))
    if perspective_content is not None:
        next_state["perspective_content"] = perspective_content

    final_document = safe_document(graph_state.get("final_document") or graph_state.get("finalDocument"))
    if final_document is not None:
        next_state["final_document"] = final_document

    return next_state


def serialize_graph_state(state: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "research_idea": str(state.get("research_idea") or "").strip(),
    }
    outline = safe_outline(state.get("document_outline"))
    if outline is not None:
        payload["document_outline"] = outline.model_dump(mode="json")

    perspectives = safe_perspectives(state.get("perspectives"))
    if perspectives is not None:
        payload["perspectives"] = perspectives.model_dump(mode="json")

    perspective_content = normalize_nested_string_rows(state.get("perspective_content"))
    if perspective_content is not None:
        payload["perspective_content"] = perspective_content

    final_document = safe_document(state.get("final_document"))
    if final_document is not None:
        payload["final_document"] = final_document.model_dump(mode="json")

    return payload


def next_node_after(node_sequence: tuple[str, ...], node_name: str) -> str | None:
    normalized = str(node_name or "").strip()
    if normalized not in node_sequence:
        return None
    index = node_sequence.index(normalized)
    if index >= len(node_sequence) - 1:
        return None
    return node_sequence[index + 1]


def default_resume_node_for_state(state: dict[str, Any]) -> str | None:
    if not state.get("document_outline"):
        return "generate_document_outline"
    if not state.get("perspectives"):
        return "generate_perspectives"
    if not state.get("perspective_content"):
        return "generate_content_for_perspectives"
    if not state.get("final_document"):
        return "final_section_generation"
    return None


def resolve_resume_node(
    node_sequence: tuple[str, ...],
    requested_node: str | None,
    state: dict[str, Any],
) -> str | None:
    normalized = str(requested_node or "").strip()
    if not normalized:
        return default_resume_node_for_state(state)
    if normalized not in node_sequence:
        return default_resume_node_for_state(state)

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
    return default_resume_node_for_state(state)
