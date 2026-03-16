from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from structures import CompleteDocument, ContentSection

from ..helpers import (
    extract_agent_text_content,
    fallback_section_text,
    is_structured_output_error,
    message_text,
)
from .expert_context import (
    EXPERT_CONTEXT_SUMMARY_PROMPT,
    maybe_compact_agent_thread_history as _maybe_compact_agent_thread_history,
)


def build_agent_run_config(
    base_config: dict[str, Any] | None,
    thread_id: str,
) -> dict[str, Any]:
    config = dict(base_config or {})
    configurable = dict(config.get("configurable") or {})
    configurable["thread_id"] = str(thread_id)
    config["configurable"] = configurable

    metadata = dict(config.get("metadata") or {})
    metadata["agent_thread_id"] = str(thread_id)
    config["metadata"] = metadata
    return config


def is_context_window_error(error: Exception) -> bool:
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    markers = (
        "context window",
        "context_length_exceeded",
        "maximum context length",
        "too many tokens",
        "input tokens",
        "prompt is too long",
        "requested too many tokens",
        "token limit",
    )

    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))

        candidate_strings = [
            str(current or ""),
            str(getattr(current, "code", "") or ""),
            str(getattr(current, "type", "") or ""),
            str(getattr(current, "param", "") or ""),
            str(getattr(current, "body", "") or ""),
            str(getattr(current, "response", "") or ""),
        ]
        for candidate in candidate_strings:
            text = candidate.lower()
            if any(marker in text for marker in markers):
                return True

        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            pending.append(cause)

        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            pending.append(context)

        for nested in getattr(current, "exceptions", ()) or ():
            if isinstance(nested, BaseException):
                pending.append(nested)

    return False


def retry_delay_for_index(delays: tuple[float, ...], retry_index: int) -> float:
    if len(delays) == 0:
        return 0.0
    if retry_index < len(delays):
        return max(float(delays[retry_index]), 0.0)
    return max(float(delays[-1]), 0.0)


def build_section_thread_id(expert_index: int, section_index: int, cold_generation: int) -> str:
    return (
        f"research-expert-{expert_index + 1}-"
        f"section-{section_index + 1}-"
        f"cold-{cold_generation}"
    )


def normalize_saved_section_results(
    saved_progress: dict[str, Any] | None,
    sections: list,
) -> list[dict[str, str]]:
    if not isinstance(saved_progress, dict):
        return []

    raw_results = saved_progress.get("section_results")
    if not isinstance(raw_results, list):
        return []

    normalized: list[dict[str, str]] = []
    for section_index, raw_result in enumerate(raw_results[: len(sections)]):
        if not isinstance(raw_result, dict):
            continue
        status = str(raw_result.get("status") or "completed").strip().lower()
        if status not in {"completed", "skipped"}:
            status = "completed"
        normalized.append(
            {
                "status": status,
                "content": str(raw_result.get("content") or ""),
            }
        )
    return normalized


def build_history_from_section_results(
    sections: list,
    section_results: list[dict[str, str]],
    expert_name: str,
) -> list[str]:
    history: list[str] = []
    for section_index, result in enumerate(section_results[: len(sections)]):
        section = sections[section_index]
        section_title = str(getattr(section, "section_title", f"Section {section_index + 1}") or f"Section {section_index + 1}")
        content = str(result.get("content") or "").strip()
        if str(result.get("status") or "") == "skipped":
            content = (
                content
                or f"{expert_name} skipped this section after repeated generation failures."
            )
        elif not content:
            content = fallback_section_text(section_title)
        history.append(f"## {section_title}\n\n{content}".strip())
    return history


async def invoke_section_agent(
    agent: object,
    prompt: str,
    *,
    run_config: dict[str, Any] | None = None,
) -> dict:
    return await agent.ainvoke({"messages": [HumanMessage(content=prompt)]}, config=run_config)


async def compact_agent_thread_history(
    *,
    agent: object,
    summary_model: Any,
    thread_config: dict[str, Any],
    trigger_tokens: int = 1,
    keep_last_messages: int,
    trim_tokens_to_summarize: int | None = None,
    summary_config: dict[str, Any] | None = None,
    force: bool = True,
    timeout_seconds: float | None = None,
) -> bool:
    awaitable = _maybe_compact_agent_thread_history(
        agent=agent,
        summary_model=summary_model,
        thread_config=thread_config,
        trigger_tokens=trigger_tokens,
        keep_last_messages=keep_last_messages,
        trim_tokens_to_summarize=trim_tokens_to_summarize,
        summary_prompt=EXPERT_CONTEXT_SUMMARY_PROMPT,
        summary_config=summary_config,
        force=force,
    )
    if timeout_seconds is None or timeout_seconds <= 0:
        return await awaitable
    try:
        return await asyncio.wait_for(awaitable, timeout=float(timeout_seconds))
    except asyncio.TimeoutError:
        print("[graph] Agent thread compaction timed out.")
        return False


async def generate_section_with_retry_policy(
    *,
    agent: object,
    summary_model: Any,
    prompt: str,
    section_title: str,
    expert_label: str,
    expert_index: int,
    section_index: int,
    section_retry_delays: tuple[float, ...],
    section_attempt_timeout_seconds: float,
    section_context_trigger_tokens: int,
    section_context_keep_messages: int,
    section_context_trim_tokens_to_summarize: int | None,
    summary_timeout_seconds: float,
    emit_progress: Any = None,
    run_config: dict[str, Any] | None = None,
) -> tuple[str, str]:
    warm_retry_budget = 2
    cold_retry_budget = 2
    retry_counter = 0
    thread_generation = 0
    thread_id = build_section_thread_id(expert_index, section_index, thread_generation)
    thread_config = build_agent_run_config(run_config, thread_id)

    async def _emit_status(message: str) -> None:
        if emit_progress is None:
            return
        await emit_progress("generate_content_for_perspectives", message)

    for warm_attempt in range(warm_retry_budget + 1):
        attempt_label = "initial attempt" if warm_attempt == 0 else f"warm retry {warm_attempt}/{warm_retry_budget}"
        await _emit_status(
            f"{expert_label}: generating '{section_title}' ({attempt_label})."
        )
        try:
            proactively_compacted = await compact_agent_thread_history(
                agent=agent,
                summary_model=summary_model,
                thread_config=thread_config,
                trigger_tokens=section_context_trigger_tokens,
                keep_last_messages=section_context_keep_messages,
                trim_tokens_to_summarize=section_context_trim_tokens_to_summarize,
                summary_config=run_config,
                force=False,
                timeout_seconds=summary_timeout_seconds,
            )
            if proactively_compacted:
                await _emit_status(
                    f"{expert_label}: compacted existing context for '{section_title}' before {attempt_label}."
                )
            result = await asyncio.wait_for(
                invoke_section_agent(agent=agent, prompt=prompt, run_config=thread_config),
                timeout=section_attempt_timeout_seconds,
            )
            content_text = extract_agent_text_content(result).strip()
            if content_text:
                return content_text, "completed"
            raise ValueError("Generated section content was empty.")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if warm_attempt >= warm_retry_budget:
                break

            if is_context_window_error(error):
                await _emit_status(
                    f"{expert_label}: compacting context for '{section_title}' before warm retry {warm_attempt + 1}/{warm_retry_budget}."
                )
                await compact_agent_thread_history(
                    agent=agent,
                    summary_model=summary_model,
                    thread_config=thread_config,
                    trigger_tokens=section_context_trigger_tokens,
                    keep_last_messages=section_context_keep_messages,
                    trim_tokens_to_summarize=section_context_trim_tokens_to_summarize,
                    summary_config=run_config,
                    force=True,
                    timeout_seconds=summary_timeout_seconds,
                )

            delay = retry_delay_for_index(section_retry_delays, retry_counter)
            retry_counter += 1
            print(
                f"[graph] Expert '{expert_label}' failed during {attempt_label} for "
                f"section '{section_title}': {error}. Retrying same thread in {delay:.1f}s."
            )
            if delay > 0:
                await asyncio.sleep(delay)

    for cold_retry in range(1, cold_retry_budget + 1):
        thread_generation = cold_retry
        thread_id = build_section_thread_id(expert_index, section_index, thread_generation)
        thread_config = build_agent_run_config(run_config, thread_id)
        await _emit_status(
            f"{expert_label}: cold retry {cold_retry}/{cold_retry_budget} for '{section_title}'."
        )
        try:
            proactively_compacted = await compact_agent_thread_history(
                agent=agent,
                summary_model=summary_model,
                thread_config=thread_config,
                trigger_tokens=section_context_trigger_tokens,
                keep_last_messages=section_context_keep_messages,
                trim_tokens_to_summarize=section_context_trim_tokens_to_summarize,
                summary_config=run_config,
                force=False,
                timeout_seconds=summary_timeout_seconds,
            )
            if proactively_compacted:
                await _emit_status(
                    f"{expert_label}: compacted existing context for '{section_title}' before cold retry {cold_retry}/{cold_retry_budget}."
                )
            result = await asyncio.wait_for(
                invoke_section_agent(agent=agent, prompt=prompt, run_config=thread_config),
                timeout=section_attempt_timeout_seconds,
            )
            content_text = extract_agent_text_content(result).strip()
            if content_text:
                return content_text, "completed"
            raise ValueError("Generated section content was empty.")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if cold_retry >= cold_retry_budget:
                print(
                    f"[graph] Expert '{expert_label}' failed for section '{section_title}' "
                    "after 1 initial attempt, 2 warm retries, and 2 cold retries. "
                    f"Skipping section. Last error: {error}"
                )
                break

            delay = retry_delay_for_index(section_retry_delays, retry_counter)
            retry_counter += 1
            print(
                f"[graph] Expert '{expert_label}' cold retry {cold_retry}/{cold_retry_budget} "
                f"failed for section '{section_title}': {error}. Retrying from scratch in {delay:.1f}s."
            )
            if delay > 0:
                await asyncio.sleep(delay)

    await _emit_status(f"{expert_label}: skipped '{section_title}' after exhausting retries.")
    return "", "skipped"


async def run_expert_pipeline(
    *,
    expert_index: int,
    expert_name: str,
    expert_agent: object,
    sections: list,
    saved_progress: dict[str, Any] | None,
    emit_progress: Any,
    persist_progress: Any,
    summary_model: Any,
    node_builder: Any,
    section_retry_delays: tuple[float, ...],
    section_attempt_timeout_seconds: float,
    section_context_trigger_tokens: int,
    section_context_keep_messages: int,
    section_context_trim_tokens_to_summarize: int | None,
    summary_timeout_seconds: float,
    run_config: dict[str, Any] | None = None,
) -> list[str]:
    print(f"[graph] Expert pipeline started: index={expert_index}, name='{expert_name}'")

    section_results = normalize_saved_section_results(saved_progress, sections)
    pipeline_outputs = [str(result.get("content") or "") for result in section_results]
    expert_history = build_history_from_section_results(sections, section_results, expert_name)
    summary = str((saved_progress or {}).get("summary") or "").strip() or None

    if 0 < len(section_results) < len(sections) and emit_progress is not None:
        await emit_progress(
            "generate_content_for_perspectives",
            (
                f"{expert_name}: resuming from section "
                f"{min(len(section_results), len(sections)) + 1}/{max(len(sections), 1)}."
            ),
        )

    for section_index in range(len(section_results), len(sections)):
        section = sections[section_index]
        section_title = str(getattr(section, "section_title", "Untitled Section") or "Untitled Section")
        prompt = f"Write the content for the section:\n{section.as_str}"
        if summary:
            prompt += f"\n\nSummary of the previous sections:\n{summary}"

        section_text, status = await generate_section_with_retry_policy(
            agent=expert_agent,
            summary_model=summary_model,
            prompt=prompt,
            section_title=section_title,
            expert_label=expert_name,
            expert_index=expert_index,
            section_index=section_index,
            section_retry_delays=section_retry_delays,
            section_attempt_timeout_seconds=section_attempt_timeout_seconds,
            section_context_trigger_tokens=section_context_trigger_tokens,
            section_context_keep_messages=section_context_keep_messages,
            section_context_trim_tokens_to_summarize=section_context_trim_tokens_to_summarize,
            summary_timeout_seconds=summary_timeout_seconds,
            emit_progress=emit_progress,
            run_config=run_config,
        )

        section_results.append({"status": status, "content": section_text})
        pipeline_outputs.append(section_text)

        history_text = section_text.strip()
        if status == "skipped":
            history_text = (
                history_text
                or f"{expert_name} skipped this section after repeated generation failures."
            )
        elif not history_text:
            history_text = fallback_section_text(section_title)
        expert_history.append(f"## {section_title}\n\n{history_text}".strip())

        try:
            summary_message = await asyncio.wait_for(
                summary_model.ainvoke(
                    node_builder.generate_rolling_summary("\n\n".join(expert_history)),
                    config=run_config,
                ),
                timeout=float(summary_timeout_seconds),
            )
            next_summary = message_text(summary_message).strip()
            if next_summary:
                summary = next_summary
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            print(
                f"[graph] Summary update timed out for expert '{expert_name}' "
                f"after section '{section_title}'. Continuing with prior summary."
            )
        except Exception as error:
            print(
                f"[graph] Summary update failed for expert '{expert_name}' "
                f"after section '{section_title}': {error}. Continuing with prior summary."
            )

        if persist_progress is not None:
            await persist_progress(
                {
                    "expert_name": expert_name,
                    "summary": summary or "",
                    "section_results": list(section_results),
                },
                (
                    f"{expert_name}: completed section "
                    f"{section_index + 1}/{len(sections)}."
                ),
            )

    print(
        f"[graph] Expert pipeline completed: index={expert_index}, "
        f"name='{expert_name}', sections={len(pipeline_outputs)}"
    )
    return pipeline_outputs


async def generate_final_section(
    *,
    section_content: list[str],
    outline_str: str,
    summary: str | None,
    node_builder: Any,
    final_content_model: Any,
    run_config: dict[str, Any] | None = None,
) -> ContentSection:
    messages = node_builder.generate_combined_section(
        "\n\n".join(section_content),
        outline_str,
        summary,
    )

    try:
        return await final_content_model.with_structured_output(ContentSection).ainvoke(
            messages,
            config=run_config,
        )
    except Exception as error:
        if not is_structured_output_error(error):
            raise

    return await final_content_model.with_structured_output(ContentSection).ainvoke(
        messages,
        config=run_config,
    )


def build_low_breadth_document(state: dict[str, Any]) -> CompleteDocument:
    sections = list(state["document_outline"].sections)
    perspective_rows = list(state.get("perspective_content", []))
    final_sections: list[ContentSection] = []

    for section_index, outline_section in enumerate(sections):
        section_title = str(
            getattr(outline_section, "section_title", f"Section {section_index + 1}")
            or f"Section {section_index + 1}"
        )
        section_text = ""
        if section_index < len(perspective_rows) and perspective_rows[section_index]:
            section_text = str(perspective_rows[section_index][0] or "").strip()
        if not section_text:
            section_text = fallback_section_text(section_title)

        final_sections.append(
            ContentSection(
                section_title=section_title,
                content=section_text,
                citations=[],
            )
        )

    return CompleteDocument(
        title=state["document_outline"].document_title,
        sections=final_sections,
    )
