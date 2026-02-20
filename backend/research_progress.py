from typing import Final


RESEARCH_NODE_PROGRESS_MESSAGES: Final[dict[str, str]] = {
    "queued": "Research queued. Waiting to start.",
    "preparing": "Preparing your research workflow.",
    "generate_document_outline": "Analyzing your request, gathering context, and drafting an outline.",
    "generate_perspectives": "Ensuring all important angles of your idea are covered.",
    "generate_content_for_perspectives": "Performing deep, well-rounded research to collect information.",
    "final_section_generation": "Writing your final research document.",
    "completed": "Research completed.",
    "failed": "Research could not be completed.",
}


def normalize_research_node(node: str | None) -> str | None:
    value = str(node or "").strip()
    if not value:
        return None
    return value


def progress_message_for_node(node: str | None, fallback: str | None = None) -> str:
    normalized = normalize_research_node(node)
    if normalized is None:
        return str(fallback or "Research is in progress.")
    return RESEARCH_NODE_PROGRESS_MESSAGES.get(normalized, str(fallback or "Research is in progress."))
