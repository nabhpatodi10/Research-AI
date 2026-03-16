from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AnyMessage, BaseMessage, HumanMessage, RemoveMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from ..helpers import message_text


EXPERT_CONTEXT_SUMMARY_PROMPT = """
Summarize the prior conversation context for a specialist research agent.

You must preserve critical information with high fidelity. Do not fabricate information.
If a section has nothing relevant, write "None".

Use exactly this structure:

## SESSION GOAL
State the overall research objective and what this specialist is currently trying to produce.

## REQUIRED CONSTRAINTS
Capture all explicit constraints and requirements (formatting, scope, exclusions, quality bars, citation rules, equation/chart requirements, etc.).

## KEY DECISIONS
List important decisions already made, including rationale when present.

## TOOL FINDINGS
Summarize important tool outcomes and factual findings, including contradictions or uncertainty.

## SOURCES / CITATIONS
List important URLs or source references already established.

## OPEN QUESTIONS / ASSUMPTIONS
Capture unresolved questions, assumptions, and pending clarifications.

## EXECUTION STATE
Describe what has already been completed and what remains to be done next.

Return only the structured summary.

Messages to summarize:
{messages}
""".strip()

SUMMARY_PREFIX = "Summary of earlier section work, tool calls, and findings:\n"


def count_message_tokens(messages: Sequence[AnyMessage | BaseMessage]) -> int:
    return count_tokens_approximately(list(messages))


def format_messages_for_summary(messages: Sequence[BaseMessage]) -> str:
    lines: list[str] = []
    for message in messages:
        role = str(
            getattr(message, "type", message.__class__.__name__) or message.__class__.__name__
        )
        content = message_text(message).strip()
        if not content:
            continue
        lines.append(f"{role.upper()}: {content}")
    return "\n\n".join(lines).strip()


def trim_messages_to_token_budget(
    messages: Sequence[BaseMessage],
    max_tokens: int | None,
) -> list[BaseMessage]:
    normalized = list(messages)
    if max_tokens is None or max_tokens <= 0 or len(normalized) <= 1:
        return normalized

    selected: list[BaseMessage] = []
    total_tokens = 0
    for message in reversed(normalized):
        message_tokens = count_message_tokens([message])
        if selected and total_tokens + message_tokens > max_tokens:
            break
        selected.append(message)
        total_tokens += message_tokens
    if len(selected) == 0:
        return [normalized[-1]]
    return list(reversed(selected))


async def _call_summary_model_async(
    summary_model: Any,
    prompt: str,
    *,
    summary_config: dict[str, Any] | None,
) -> str:
    summary_message = await summary_model.ainvoke(prompt, config=summary_config)
    return message_text(summary_message).strip()


def _call_summary_model_sync(
    summary_model: Any,
    prompt: str,
    *,
    summary_config: dict[str, Any] | None,
) -> str:
    if not hasattr(summary_model, "invoke"):
        return ""
    summary_message = summary_model.invoke(prompt, config=summary_config)
    return message_text(summary_message).strip()


async def summarize_messages_async(
    summary_model: Any,
    messages: Sequence[BaseMessage],
    *,
    trim_tokens_to_summarize: int | None,
    summary_prompt: str,
    summary_config: dict[str, Any] | None = None,
) -> str:
    trimmed_messages = trim_messages_to_token_budget(messages, trim_tokens_to_summarize)
    summary_input = format_messages_for_summary(trimmed_messages)
    if not summary_input:
        return ""
    return await _call_summary_model_async(
        summary_model,
        summary_prompt.format(messages=summary_input),
        summary_config=summary_config,
    )


def summarize_messages_sync(
    summary_model: Any,
    messages: Sequence[BaseMessage],
    *,
    trim_tokens_to_summarize: int | None,
    summary_prompt: str,
    summary_config: dict[str, Any] | None = None,
) -> str:
    trimmed_messages = trim_messages_to_token_budget(messages, trim_tokens_to_summarize)
    summary_input = format_messages_for_summary(trimmed_messages)
    if not summary_input:
        return ""
    return _call_summary_model_sync(
        summary_model,
        summary_prompt.format(messages=summary_input),
        summary_config=summary_config,
    )


def _build_replacement_messages(
    preserved_messages: Sequence[BaseMessage],
    summary_text: str,
) -> list[BaseMessage]:
    replacement_messages: list[BaseMessage] = []
    if summary_text:
        replacement_messages.append(
            HumanMessage(content=f"{SUMMARY_PREFIX}{summary_text}")
        )
    replacement_messages.extend(list(preserved_messages))
    return replacement_messages


async def maybe_summarize_messages_async(
    summary_model: Any,
    messages: Sequence[AnyMessage | BaseMessage],
    *,
    trigger_tokens: int,
    keep_last_messages: int,
    trim_tokens_to_summarize: int | None,
    summary_prompt: str,
    summary_config: dict[str, Any] | None = None,
    force: bool = False,
) -> list[BaseMessage] | None:
    normalized_messages = [message for message in messages if isinstance(message, BaseMessage)]
    if len(normalized_messages) <= keep_last_messages:
        return None

    if not force and count_message_tokens(normalized_messages) < max(1, int(trigger_tokens)):
        return None

    older_messages = normalized_messages[:-keep_last_messages]
    preserved_messages = normalized_messages[-keep_last_messages:]
    if len(older_messages) == 0:
        return None

    summary_text = await summarize_messages_async(
        summary_model,
        older_messages,
        trim_tokens_to_summarize=trim_tokens_to_summarize,
        summary_prompt=summary_prompt,
        summary_config=summary_config,
    )
    return _build_replacement_messages(preserved_messages, summary_text)


def maybe_summarize_messages_sync(
    summary_model: Any,
    messages: Sequence[AnyMessage | BaseMessage],
    *,
    trigger_tokens: int,
    keep_last_messages: int,
    trim_tokens_to_summarize: int | None,
    summary_prompt: str,
    summary_config: dict[str, Any] | None = None,
    force: bool = False,
) -> list[BaseMessage] | None:
    normalized_messages = [message for message in messages if isinstance(message, BaseMessage)]
    if len(normalized_messages) <= keep_last_messages:
        return None

    if not force and count_message_tokens(normalized_messages) < max(1, int(trigger_tokens)):
        return None

    older_messages = normalized_messages[:-keep_last_messages]
    preserved_messages = normalized_messages[-keep_last_messages:]
    if len(older_messages) == 0:
        return None

    summary_text = summarize_messages_sync(
        summary_model,
        older_messages,
        trim_tokens_to_summarize=trim_tokens_to_summarize,
        summary_prompt=summary_prompt,
        summary_config=summary_config,
    )
    return _build_replacement_messages(preserved_messages, summary_text)


async def maybe_compact_agent_thread_history(
    *,
    agent: object,
    summary_model: Any,
    thread_config: dict[str, Any],
    trigger_tokens: int,
    keep_last_messages: int,
    trim_tokens_to_summarize: int | None,
    summary_prompt: str,
    summary_config: dict[str, Any] | None = None,
    force: bool = False,
) -> bool:
    if (
        keep_last_messages <= 0
        or not hasattr(agent, "get_state")
        or not hasattr(agent, "update_state")
    ):
        return False

    try:
        snapshot = agent.get_state(thread_config)
        state_values = getattr(snapshot, "values", {}) if snapshot is not None else {}
        messages = list(state_values.get("messages") or [])
    except Exception as error:
        print(f"[graph] Failed to inspect agent thread for compaction: {error}")
        return False

    try:
        replacement_messages = await maybe_summarize_messages_async(
            summary_model,
            messages,
            trigger_tokens=trigger_tokens,
            keep_last_messages=keep_last_messages,
            trim_tokens_to_summarize=trim_tokens_to_summarize,
            summary_prompt=summary_prompt,
            summary_config=summary_config,
            force=force,
        )
    except Exception as error:
        print(f"[graph] Agent thread compaction summary failed: {error}")
        return False

    if replacement_messages is None:
        return False

    try:
        agent.update_state(
            thread_config,
            {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *replacement_messages]},
            as_node="model",
        )
    except Exception as error:
        print(f"[graph] Failed to compact agent thread history: {error}")
        return False

    return True


class ExpertContextSummarizationMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        summary_model: Any,
        trigger_tokens: int,
        keep_last_messages: int,
        trim_tokens_to_summarize: int | None,
        summary_prompt: str = EXPERT_CONTEXT_SUMMARY_PROMPT,
    ) -> None:
        super().__init__()
        self.summary_model = summary_model
        self.trigger_tokens = max(1, int(trigger_tokens))
        self.keep_last_messages = max(1, int(keep_last_messages))
        self.trim_tokens_to_summarize = (
            None
            if trim_tokens_to_summarize is None
            else max(1, int(trim_tokens_to_summarize))
        )
        self.summary_prompt = summary_prompt

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ):
        replacement_messages = maybe_summarize_messages_sync(
            self.summary_model,
            request.messages,
            trigger_tokens=self.trigger_tokens,
            keep_last_messages=self.keep_last_messages,
            trim_tokens_to_summarize=self.trim_tokens_to_summarize,
            summary_prompt=self.summary_prompt,
        )
        if replacement_messages is None:
            return handler(request)
        return handler(request.override(messages=replacement_messages))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ):
        replacement_messages = await maybe_summarize_messages_async(
            self.summary_model,
            request.messages,
            trigger_tokens=self.trigger_tokens,
            keep_last_messages=self.keep_last_messages,
            trim_tokens_to_summarize=self.trim_tokens_to_summarize,
            summary_prompt=self.summary_prompt,
        )
        if replacement_messages is None:
            return await handler(request)
        return await handler(request.override(messages=replacement_messages))


__all__ = [
    "EXPERT_CONTEXT_SUMMARY_PROMPT",
    "ExpertContextSummarizationMiddleware",
    "count_message_tokens",
    "format_messages_for_summary",
    "maybe_compact_agent_thread_history",
    "maybe_summarize_messages_async",
    "maybe_summarize_messages_sync",
]
