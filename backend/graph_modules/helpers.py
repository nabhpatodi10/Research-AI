from langchain_core.messages import AIMessage


def expert_count_for_breadth(research_breadth: str) -> int:
    if research_breadth == "low":
        return 1
    if research_breadth == "high":
        return 5
    return 3


def extract_structured_response(result: dict, expected_type: type):
    structured = result.get("structured_response") if isinstance(result, dict) else None
    if isinstance(structured, expected_type):
        return structured
    raise ValueError(f"Agent did not return a structured response of type {expected_type.__name__}.")


def message_text(message: object) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str) and text:
        return text
    return str(getattr(message, "content", "")).strip()


def is_structured_output_error(error: Exception) -> bool:
    error_name = error.__class__.__name__
    error_text = str(error)
    return (
        error_name == "StructuredOutputValidationError"
        or "StructuredOutputValidationError" in error_text
        or "Failed to parse structured output" in error_text
    )


def fallback_section_text(section_title: str) -> str:
    return f"Could not generate section content for '{section_title}' due to repeated generation failures."


def extract_agent_text_content(result: dict) -> str:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return ""

    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = message_text(message)
            if text:
                return text

    return message_text(messages[-1])
