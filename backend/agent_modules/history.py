import asyncio
from typing import Any

from langchain.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from database import Database
from nodes import Nodes

from .helpers import message_role, message_text


async def summarize_older_messages(
    messages: list[BaseMessage],
    model: BaseChatModel,
    run_config: dict[str, Any] | None = None,
) -> AIMessage | None:
    if not messages:
        return None

    max_chars = 48000
    transcript_lines: list[str] = []
    used_chars = 0
    for message in messages:
        text = message_text(message)
        if not text:
            continue
        line = f"{message_role(message)}: {text}"
        if used_chars + len(line) > max_chars:
            break
        transcript_lines.append(line)
        used_chars += len(line)

    if not transcript_lines:
        return None

    try:
        summary_response = await model.ainvoke(
            Nodes().generate_conversation_summary(transcript_lines),
            config=run_config,
        )
        summary_text = message_text(summary_response)
    except Exception:
        summary_text = "\n".join(transcript_lines[-12:])

    if not summary_text:
        return None

    return AIMessage(content=f"Summary of earlier conversation before latest 5 turns:\n{summary_text}")


async def get_chat_history(
    database: Database,
    session_id: str,
    model: BaseChatModel,
    run_config: dict[str, Any] | None = None,
) -> list[BaseMessage]:
    previous_messages = await database.get_messages(session_id)
    recent_history: list[BaseMessage] = []
    older_history: list[BaseMessage] = []
    if not previous_messages:
        return recent_history

    conversation_turns = 5
    for idx, message in enumerate(reversed(previous_messages), start=1):
        if not isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
            continue

        if conversation_turns > 0:
            recent_history.insert(0, message)
            if isinstance(message, HumanMessage):
                conversation_turns -= 1
        else:
            older_history.insert(0, message)

        if idx % 100 == 0:
            await asyncio.sleep(0)

    summary_message = await summarize_older_messages(older_history, model, run_config=run_config)
    if summary_message is not None:
        return [summary_message, *recent_history]
    return recent_history


async def build_research_handoff_context(
    database: Database,
    session_id: str,
    model: BaseChatModel,
    additional_user_context: str | None = None,
    run_config: dict[str, Any] | None = None,
) -> str:
    history = await get_chat_history(database, session_id, model, run_config=run_config)
    transcript_lines: list[str] = []
    for message in history:
        if not isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
            continue
        text = message_text(message)
        if not text:
            continue
        transcript_lines.append(f"{message_role(message)}: {text}")

    latest_context = str(additional_user_context or "").strip()
    if latest_context:
        transcript_lines.append(f"Latest user context: {latest_context}")

    if not transcript_lines:
        return latest_context

    summarize_prompt: list[BaseMessage] = Nodes().generate_research_handoff_brief(transcript_lines)
    try:
        summary_response = await model.ainvoke(summarize_prompt, config=run_config)
        summary_text = message_text(summary_response).strip()
        if summary_text:
            return summary_text
    except Exception:
        pass

    fallback = "\n\n".join(transcript_lines[-12:]).strip()
    return fallback or latest_context
