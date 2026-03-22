from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langchain_core.messages.utils import get_buffer_string
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


def _build_summary_config(summary_config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(summary_config or {})
    metadata = dict(config.get("metadata") or {})
    metadata["lc_source"] = "summarization"
    config["metadata"] = metadata
    return config


def _normalize_thread_messages(messages: Sequence[AnyMessage | BaseMessage]) -> list[BaseMessage]:
    return [message for message in messages if isinstance(message, BaseMessage)]


def thread_has_invalid_tool_call_state(
    messages: Sequence[AnyMessage | BaseMessage],
) -> bool:
    normalized_messages = _normalize_thread_messages(messages)
    pending_tool_call_ids: set[str] = set()

    for message in normalized_messages:
        if isinstance(message, ToolMessage):
            tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
            if not tool_call_id or tool_call_id not in pending_tool_call_ids:
                return True
            pending_tool_call_ids.remove(tool_call_id)
            continue

        if pending_tool_call_ids:
            return True

        if isinstance(message, AIMessage):
            for tool_call in getattr(message, "tool_calls", None) or []:
                tool_call_id = ""
                if isinstance(tool_call, dict):
                    tool_call_id = str(tool_call.get("id") or "").strip()
                else:
                    tool_call_id = str(getattr(tool_call, "id", "") or "").strip()
                if tool_call_id:
                    pending_tool_call_ids.add(tool_call_id)

    return len(pending_tool_call_ids) > 0


class HighFidelityExpertSummarizationMiddleware(SummarizationMiddleware):
    def __init__(
        self,
        *,
        summary_model: Any,
        trigger_tokens: int,
        keep_last_messages: int,
        trim_tokens_to_summarize: int | None,
        summary_prompt: str = EXPERT_CONTEXT_SUMMARY_PROMPT,
    ) -> None:
        normalized_trigger_tokens = max(1, int(trigger_tokens))
        normalized_keep_last_messages = max(1, int(keep_last_messages))
        normalized_trim_tokens = (
            None
            if trim_tokens_to_summarize is None
            else max(1, int(trim_tokens_to_summarize))
        )
        super().__init__(
            model=summary_model,
            trigger=("tokens", normalized_trigger_tokens),
            keep=("messages", normalized_keep_last_messages),
            trim_tokens_to_summarize=normalized_trim_tokens,
            summary_prompt=summary_prompt,
        )
        self.summary_model = summary_model
        self.trigger_tokens = normalized_trigger_tokens
        self.keep_last_messages = normalized_keep_last_messages
        self.trim_tokens_to_summarize = normalized_trim_tokens
        self.summary_prompt = summary_prompt

    @staticmethod
    def _build_new_messages(summary: str) -> list[HumanMessage]:
        return [
            HumanMessage(
                content=f"{SUMMARY_PREFIX}{summary}",
                additional_kwargs={"lc_source": "summarization"},
            )
        ]

    def _create_summary_with_config(
        self,
        messages_to_summarize: list[AnyMessage],
        *,
        summary_config: dict[str, Any] | None = None,
    ) -> str:
        if not messages_to_summarize:
            return "No previous conversation history."

        trimmed_messages = self._trim_messages_for_summary(messages_to_summarize)
        if not trimmed_messages:
            return "Previous conversation was too long to summarize."

        formatted_messages = get_buffer_string(trimmed_messages)
        try:
            response = self.model.invoke(
                self.summary_prompt.format(messages=formatted_messages).rstrip(),
                config=_build_summary_config(summary_config),
            )
            return message_text(response).strip()
        except Exception as error:
            return f"Error generating summary: {error!s}"

    async def _acreate_summary_with_config(
        self,
        messages_to_summarize: list[AnyMessage],
        *,
        summary_config: dict[str, Any] | None = None,
    ) -> str:
        if not messages_to_summarize:
            return "No previous conversation history."

        trimmed_messages = self._trim_messages_for_summary(messages_to_summarize)
        if not trimmed_messages:
            return "Previous conversation was too long to summarize."

        formatted_messages = get_buffer_string(trimmed_messages)
        try:
            response = await self.model.ainvoke(
                self.summary_prompt.format(messages=formatted_messages).rstrip(),
                config=_build_summary_config(summary_config),
            )
            return message_text(response).strip()
        except Exception as error:
            return f"Error generating summary: {error!s}"

    def rewrite_messages(
        self,
        messages: Sequence[AnyMessage | BaseMessage],
        *,
        force: bool = False,
        summary_config: dict[str, Any] | None = None,
    ) -> list[BaseMessage] | None:
        normalized_messages = _normalize_thread_messages(messages)
        if not normalized_messages:
            return None

        self._ensure_message_ids(normalized_messages)

        total_tokens = self.token_counter(normalized_messages)
        if not force and not self._should_summarize(normalized_messages, total_tokens):
            return None

        cutoff_index = self._determine_cutoff_index(normalized_messages)
        if cutoff_index <= 0:
            return None

        messages_to_summarize, preserved_messages = self._partition_messages(
            normalized_messages,
            cutoff_index,
        )
        summary = self._create_summary_with_config(
            messages_to_summarize,
            summary_config=summary_config,
        )
        return [*self._build_new_messages(summary), *preserved_messages]

    async def arewrite_messages(
        self,
        messages: Sequence[AnyMessage | BaseMessage],
        *,
        force: bool = False,
        summary_config: dict[str, Any] | None = None,
    ) -> list[BaseMessage] | None:
        normalized_messages = _normalize_thread_messages(messages)
        if not normalized_messages:
            return None

        self._ensure_message_ids(normalized_messages)

        total_tokens = self.token_counter(normalized_messages)
        if not force and not self._should_summarize(normalized_messages, total_tokens):
            return None

        cutoff_index = self._determine_cutoff_index(normalized_messages)
        if cutoff_index <= 0:
            return None

        messages_to_summarize, preserved_messages = self._partition_messages(
            normalized_messages,
            cutoff_index,
        )
        summary = await self._acreate_summary_with_config(
            messages_to_summarize,
            summary_config=summary_config,
        )
        return [*self._build_new_messages(summary), *preserved_messages]

    def before_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        replacement_messages = self.rewrite_messages(state.get("messages") or [])
        if replacement_messages is None:
            return None
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *replacement_messages,
            ]
        }

    async def abefore_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        replacement_messages = await self.arewrite_messages(state.get("messages") or [])
        if replacement_messages is None:
            return None
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *replacement_messages,
            ]
        }


ExpertContextSummarizationMiddleware = HighFidelityExpertSummarizationMiddleware


def build_high_fidelity_expert_summarization_middleware(
    *,
    summary_model: Any,
    trigger_tokens: int,
    keep_last_messages: int,
    trim_tokens_to_summarize: int | None,
    summary_prompt: str = EXPERT_CONTEXT_SUMMARY_PROMPT,
) -> HighFidelityExpertSummarizationMiddleware:
    return HighFidelityExpertSummarizationMiddleware(
        summary_model=summary_model,
        trigger_tokens=trigger_tokens,
        keep_last_messages=keep_last_messages,
        trim_tokens_to_summarize=trim_tokens_to_summarize,
        summary_prompt=summary_prompt,
    )


def get_agent_thread_messages(
    *,
    agent: object,
    thread_config: dict[str, Any],
) -> list[BaseMessage]:
    snapshot = agent.get_state(thread_config)
    state_values = getattr(snapshot, "values", {}) if snapshot is not None else {}
    messages = list(state_values.get("messages") or [])
    return _normalize_thread_messages(messages)


async def replace_agent_thread_messages(
    *,
    agent: object,
    thread_config: dict[str, Any],
    replacement_messages: Sequence[BaseMessage],
) -> bool:
    if not hasattr(agent, "update_state") and not hasattr(agent, "aupdate_state"):
        return False

    update_payload = {
        "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *list(replacement_messages)]
    }
    if hasattr(agent, "aupdate_state"):
        await agent.aupdate_state(thread_config, update_payload)
        return True
    agent.update_state(thread_config, update_payload)
    return True


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
        or (not hasattr(agent, "update_state") and not hasattr(agent, "aupdate_state"))
    ):
        return False

    try:
        messages = get_agent_thread_messages(agent=agent, thread_config=thread_config)
    except Exception as error:
        print(f"[graph] Failed to inspect agent thread for compaction: {error}")
        return False

    if thread_has_invalid_tool_call_state(messages):
        print("[graph] Refusing to compact agent thread with unresolved tool-call state.")
        return False

    middleware = build_high_fidelity_expert_summarization_middleware(
        summary_model=summary_model,
        trigger_tokens=trigger_tokens,
        keep_last_messages=keep_last_messages,
        trim_tokens_to_summarize=trim_tokens_to_summarize,
        summary_prompt=summary_prompt,
    )

    try:
        replacement_messages = await middleware.arewrite_messages(
            messages,
            force=force,
            summary_config=summary_config,
        )
    except Exception as error:
        print(f"[graph] Agent thread compaction summary failed: {error}")
        return False

    if replacement_messages is None:
        return False

    try:
        return await replace_agent_thread_messages(
            agent=agent,
            thread_config=thread_config,
            replacement_messages=replacement_messages,
        )
    except Exception as error:
        print(f"[graph] Failed to compact agent thread history: {error}")
        return False


__all__ = [
    "EXPERT_CONTEXT_SUMMARY_PROMPT",
    "ExpertContextSummarizationMiddleware",
    "HighFidelityExpertSummarizationMiddleware",
    "SUMMARY_PREFIX",
    "build_high_fidelity_expert_summarization_middleware",
    "get_agent_thread_messages",
    "maybe_compact_agent_thread_history",
    "replace_agent_thread_messages",
    "thread_has_invalid_tool_call_state",
]
