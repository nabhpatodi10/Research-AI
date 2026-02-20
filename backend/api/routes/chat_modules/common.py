import re

from fastapi import Request
from langchain.chat_models import BaseChatModel
from pydantic import BaseModel

from agent import build_research_handoff_context
from nodes import Nodes
from research_progress import normalize_research_node


RESEARCH_COMMAND_PATTERN = re.compile(r"^\s*/research(?:\s+(?P<topic>[\s\S]*))?$", re.IGNORECASE)
AUTO_RESEARCH_TRIGGER_PATTERN = re.compile(
    r"\b(research|deep\s*dive|analy[sz]e|analysis|compare|comparison|benchmark|report|whitepaper|citations?|sources?)\b",
    re.IGNORECASE,
)


class AutoResearchDecision(BaseModel):
    should_handoff: bool = False
    confidence: float = 0.0


def parse_research_command(user_input: str) -> tuple[bool, str]:
    matched = RESEARCH_COMMAND_PATTERN.match(user_input or "")
    if not matched:
        return False, ""
    topic = str(matched.group("topic") or "").strip()
    return True, topic


def resolve_chat_model(request: Request, model_tier: str) -> BaseChatModel:
    if model_tier == "mini":
        return request.app.state.chat_model_mini
    return request.app.state.chat_model


def looks_like_auto_research_candidate(user_input: str) -> bool:
    text = str(user_input or "").strip()
    if not text:
        return False

    if len(text) >= 220:
        return True

    if AUTO_RESEARCH_TRIGGER_PATTERN.search(text):
        return True

    if text.count("\n") >= 3:
        return True

    return False


async def maybe_auto_research_handoff_payload(
    request: Request,
    session_id: str,
    user_input: str,
) -> str | None:
    trimmed = str(user_input or "").strip()
    if not looks_like_auto_research_candidate(trimmed):
        return None

    decision_messages = Nodes().auto_research_handoff_decision_prompt(trimmed)

    try:
        decision = await request.app.state.chat_model_mini.with_structured_output(
            AutoResearchDecision
        ).ainvoke(decision_messages)
    except Exception:
        return None

    if not isinstance(decision, AutoResearchDecision):
        return None
    if not decision.should_handoff:
        return None
    if float(decision.confidence or 0.0) < 0.55:
        return None

    handoff_context = await build_research_handoff_context(
        database=request.app.state.database,
        session_id=session_id,
        model=request.app.state.chat_model,
        additional_user_context=trimmed,
    )
    return handoff_context or trimmed


def normalize_research_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"queued", "running", "completed", "failed"}:
        return normalized
    return "failed"


async def get_active_research_task(
    request: Request,
    user_id: str,
    session_id: str,
) -> dict[str, str | None] | None:
    active_job = await request.app.state.database.get_active_research_job_for_session(session_id)
    if not isinstance(active_job, dict):
        await request.app.state.database.set_user_session_active_task(user_id, session_id, None)
        return None

    task_id = str(active_job.get("id") or "").strip()
    if not task_id:
        await request.app.state.database.set_user_session_active_task(user_id, session_id, None)
        return None

    job_status = normalize_research_status(active_job.get("status", ""))
    if job_status not in {"queued", "running"}:
        await request.app.state.database.set_user_session_active_task(user_id, session_id, None)
        return None

    current_node = normalize_research_node(active_job.get("currentNode"))
    progress_message = str(active_job.get("progressMessage") or "").strip() or None
    await request.app.state.database.set_user_session_active_task(
        user_id=user_id,
        session_id=session_id,
        task={
            "id": task_id,
            "type": "research",
            "status": job_status,
            "current_node": current_node,
            "progress_message": progress_message,
        },
    )

    return {
        "id": task_id,
        "type": "research",
        "status": job_status,
        "current_node": current_node,
        "progress_message": progress_message,
    }
