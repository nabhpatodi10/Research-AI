from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage


def message_text(message: BaseMessage) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def message_role(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "User"
    if isinstance(message, AIMessage):
        return "Assistant"
    if isinstance(message, ToolMessage):
        tool_name = message.name or "tool"
        return f"Tool({tool_name})"
    return message.__class__.__name__


def normalize_system_prompt(
    system_prompt: SystemMessage | list[SystemMessage] | str | None,
) -> SystemMessage | str | None:
    if isinstance(system_prompt, list):
        if not system_prompt:
            return None
        if len(system_prompt) == 1:
            return system_prompt[0]
        return "\n\n".join(str(message.content) for message in system_prompt)
    return system_prompt


def extract_last_ai_message(messages: list[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None
