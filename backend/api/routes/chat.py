import uuid_utils
import re
import traceback
from fastapi import APIRouter, Depends, HTTPException, Request
from langchain.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent import Agent, build_research_handoff_context
from api.models import (
    ChatMessage,
    ChatMessagesResponse,
    ChatRequest,
    ChatResponse,
    ChatSession,
    ChatSessionsResponse,
    OkResponse,
    ResearchResultResponse,
    ResearchStatusResponse,
    RenameSessionRequest,
    SessionTask,
    SessionTaskStatusResponse,
    SessionMutationResponse,
    SessionUser,
    ShareSessionRequest,
)
from api.session import get_current_user
from api.utils import derive_session_title, normalize_email
from nodes import Nodes


router = APIRouter(tags=["chat"])

RESEARCH_COMMAND_PATTERN = re.compile(r"^\s*/research(?:\s+(?P<topic>[\s\S]*))?$", re.IGNORECASE)
AUTO_RESEARCH_TRIGGER_PATTERN = re.compile(
    r"\b(research|deep\s*dive|analy[sz]e|analysis|compare|comparison|benchmark|report|whitepaper|citations?|sources?)\b",
    re.IGNORECASE,
)


class AutoResearchDecision(BaseModel):
    should_handoff: bool = False
    confidence: float = 0.0


def _parse_research_command(user_input: str) -> tuple[bool, str]:
    matched = RESEARCH_COMMAND_PATTERN.match(user_input or "")
    if not matched:
        return False, ""
    topic = str(matched.group("topic") or "").strip()
    return True, topic


def _resolve_chat_model(request: Request, model_tier: str) -> BaseChatModel:
    if model_tier == "mini":
        return request.app.state.chat_model_mini
    return request.app.state.chat_model


def _looks_like_auto_research_candidate(user_input: str) -> bool:
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


async def _maybe_auto_research_handoff_payload(
    request: Request,
    session_id: str,
    user_input: str,
) -> str | None:
    trimmed = str(user_input or "").strip()
    if not _looks_like_auto_research_candidate(trimmed):
        return None

    decision_messages = [
        HumanMessage(
            content=(
                "Decide if this user message should be handed off to a long-running deep research pipeline.\n"
                "Return should_handoff=true only when the request needs broad multi-source synthesis, "
                "comparative benchmarking, report-style output with citations/sources, or exhaustive analysis.\n"
                "Return should_handoff=false for direct Q&A, short factual answers, normal coding/debug help, "
                "or requests that can be answered quickly in one assistant response.\n\n"
                f"User message:\n{trimmed}"
            )
        )
    ]

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


def _normalize_research_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"queued", "running", "completed", "failed"}:
        return normalized
    return "failed"


async def _get_active_research_task(
    request: Request,
    user_id: str,
    session_id: str,
) -> dict[str, str] | None:
    active_task = await request.app.state.database.get_user_session_active_task(user_id, session_id)
    if not isinstance(active_task, dict):
        return None

    task_id = str(active_task.get("id") or "").strip()
    task_type = str(active_task.get("type") or "").strip().lower()
    if not task_id or task_type != "research":
        await request.app.state.database.set_user_session_active_task(user_id, session_id, None)
        return None

    job = await request.app.state.database.get_research_job_for_user(task_id, user_id)
    if job is None:
        await request.app.state.database.clear_user_session_active_task_if_matches(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
        )
        return None

    job_status = _normalize_research_status(job.get("status", ""))
    if job_status in {"completed", "failed"}:
        await request.app.state.database.clear_user_session_active_task_if_matches(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
        )
        return None

    if job_status != str(active_task.get("status") or "").strip().lower():
        await request.app.state.database.set_user_session_active_task_status(
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            status=job_status,
        )

    return {
        "id": task_id,
        "type": "research",
        "status": job_status,
    }


@router.get("/chat/sessions", response_model=ChatSessionsResponse)
async def list_chat_sessions(request: Request, current_user: SessionUser = Depends(get_current_user)):
    sessions = await request.app.state.database.list_user_sessions(current_user.id)
    return ChatSessionsResponse(sessions=[ChatSession(**session) for session in sessions])


@router.get("/chat/sessions/{session_id}/messages", response_model=ChatMessagesResponse)
async def get_chat_session_messages(
    session_id: str, request: Request, current_user: SessionUser = Depends(get_current_user)
):
    has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
    if not has_access:
        raise HTTPException(status_code=404, detail="Session not found.")
    messages = await request.app.state.database.get_session_messages_for_ui(session_id)
    return ChatMessagesResponse(messages=[ChatMessage(**message) for message in messages])


@router.patch("/chat/sessions/{session_id}", response_model=SessionMutationResponse)
async def rename_chat_session(
    session_id: str,
    payload: RenameSessionRequest,
    request: Request,
    current_user: SessionUser = Depends(get_current_user),
):
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Session topic cannot be empty.")
    if len(topic) > 120:
        raise HTTPException(status_code=400, detail="Session topic cannot exceed 120 characters.")

    has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
    if not has_access:
        raise HTTPException(status_code=404, detail="Session not found.")

    renamed = await request.app.state.database.rename_user_session(current_user.id, session_id, topic)
    if renamed is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SessionMutationResponse(ok=True, session=ChatSession(**renamed))


@router.delete("/chat/sessions/{session_id}", response_model=OkResponse)
async def delete_chat_session(
    session_id: str, request: Request, current_user: SessionUser = Depends(get_current_user)
):
    has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
    if not has_access:
        raise HTTPException(status_code=404, detail="Session not found.")
    await request.app.state.database.delete_user_session(current_user.id, session_id)
    return OkResponse(ok=True)


@router.post("/chat/sessions/{session_id}/share", response_model=OkResponse)
async def share_chat_session(
    session_id: str,
    payload: ShareSessionRequest,
    request: Request,
    current_user: SessionUser = Depends(get_current_user),
):
    has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
    if not has_access:
        raise HTTPException(status_code=404, detail="Session not found.")

    target_user = await request.app.state.database.find_user_by_email(normalize_email(payload.email))
    if target_user is None:
        raise HTTPException(status_code=404, detail="Target user not found.")
    if target_user["id"] == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot share a chat with yourself.")

    session = await request.app.state.database.get_user_session(current_user.id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    await request.app.state.database.share_session_to_user(
        from_user_id=current_user.id,
        to_user_id=target_user["id"],
        session_id=session_id,
        topic=session["topic"],
        shared_by_email=current_user.email,
    )
    return OkResponse(ok=True)


@router.get("/chat/sessions/{session_id}/task-status", response_model=SessionTaskStatusResponse)
async def get_chat_session_task_status(
    session_id: str,
    request: Request,
    current_user: SessionUser = Depends(get_current_user),
):
    has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
    if not has_access:
        raise HTTPException(status_code=404, detail="Session not found.")

    active_task = await _get_active_research_task(
        request=request,
        user_id=current_user.id,
        session_id=session_id,
    )
    if active_task is None:
        return SessionTaskStatusResponse(session_id=session_id, active_task=None)

    return SessionTaskStatusResponse(
        session_id=session_id,
        active_task=SessionTask(**active_task),
    )


@router.get("/chat/research/{research_id}/status", response_model=ResearchStatusResponse)
async def get_research_status(
    research_id: str,
    request: Request,
    current_user: SessionUser = Depends(get_current_user),
):
    job = await request.app.state.database.get_research_job_for_user(research_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research task not found.")

    session_id = str(job.get("sessionId") or "").strip()
    if not session_id:
        raise HTTPException(status_code=404, detail="Research task not found.")
    has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
    if not has_access:
        raise HTTPException(status_code=404, detail="Research task not found.")

    status = _normalize_research_status(str(job.get("status") or ""))
    if status in {"completed", "failed"}:
        await request.app.state.database.clear_user_session_active_task_if_matches(
            user_id=current_user.id,
            session_id=session_id,
            task_id=research_id,
        )

    return ResearchStatusResponse(
        research_id=research_id,
        session_id=session_id,
        status=status,
        error=(str(job.get("error")) if job.get("error") else None),
    )


@router.get("/chat/research/{research_id}/result", response_model=ResearchResultResponse)
async def get_research_result(
    research_id: str,
    request: Request,
    current_user: SessionUser = Depends(get_current_user),
):
    job = await request.app.state.database.get_research_job_for_user(research_id, current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research task not found.")

    session_id = str(job.get("sessionId") or "").strip()
    if not session_id:
        raise HTTPException(status_code=404, detail="Research task not found.")
    has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
    if not has_access:
        raise HTTPException(status_code=404, detail="Research task not found.")

    status = _normalize_research_status(str(job.get("status") or ""))
    if status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Research is not complete yet. Current status: {status}.",
        )

    response_text = str(job.get("resultText") or "").strip()
    if not response_text:
        raise HTTPException(status_code=404, detail="Research result is empty.")

    await request.app.state.database.clear_user_session_active_task_if_matches(
        user_id=current_user.id,
        session_id=session_id,
        task_id=research_id,
    )
    return ResearchResultResponse(
        research_id=research_id,
        session_id=session_id,
        response=response_text,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request_body: ChatRequest,
    request: Request,
    current_user: SessionUser = Depends(get_current_user),
):
    session_id = request_body.session_id or str(uuid_utils.uuid7())
    try:
        raw_user_input = str(request_body.user_input or "")
        trimmed_user_input = raw_user_input.strip()
        is_research_command, command_topic = _parse_research_command(raw_user_input)
        force_research_requested = bool(request_body.force_research) or is_research_command

        pending_research = False
        if request_body.session_id:
            has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
            if not has_access:
                raise HTTPException(status_code=403, detail="You do not have access to this chat session.")
            pending_research = await request.app.state.database.get_user_session_pending_research(
                current_user.id,
                session_id,
            )
            active_task = await _get_active_research_task(
                request=request,
                user_id=current_user.id,
                session_id=session_id,
            )
            if active_task is not None:
                raise HTTPException(
                    status_code=409,
                    detail="A research task is already running for this session. Wait for it to finish.",
                )

        ask_research_topic_only = False
        force_research_payload: str | None = None
        should_set_pending_research = False
        should_clear_pending_research = False

        effective_user_input = trimmed_user_input
        if pending_research and not force_research_requested:
            if not trimmed_user_input:
                raise HTTPException(status_code=400, detail="Please provide a research topic or idea.")
            effective_user_input = trimmed_user_input
            handoff_context = await build_research_handoff_context(
                database=request.app.state.database,
                session_id=session_id,
                model=request.app.state.chat_model,
                additional_user_context=trimmed_user_input,
            )
            force_research_payload = handoff_context or trimmed_user_input
            should_clear_pending_research = True
        elif force_research_requested:
            effective_user_input = command_topic if is_research_command else trimmed_user_input
            if effective_user_input:
                handoff_context = await build_research_handoff_context(
                    database=request.app.state.database,
                    session_id=session_id,
                    model=request.app.state.chat_model,
                    additional_user_context=effective_user_input,
                )
                force_research_payload = handoff_context or effective_user_input
                should_clear_pending_research = True
            elif pending_research:
                effective_user_input = "/research"
                ask_research_topic_only = True
                should_set_pending_research = True
                should_clear_pending_research = False
            else:
                handoff_context = await build_research_handoff_context(
                    database=request.app.state.database,
                    session_id=session_id,
                    model=request.app.state.chat_model,
                )
                if handoff_context:
                    effective_user_input = handoff_context
                    force_research_payload = handoff_context
                    should_clear_pending_research = True
                else:
                    effective_user_input = "/research"
                    ask_research_topic_only = True
                    should_set_pending_research = True
                    should_clear_pending_research = False
        else:
            if not trimmed_user_input:
                raise HTTPException(status_code=400, detail="Message cannot be empty.")
            effective_user_input = trimmed_user_input
            auto_handoff_payload = await _maybe_auto_research_handoff_payload(
                request=request,
                session_id=session_id,
                user_input=trimmed_user_input,
            )
            if auto_handoff_payload:
                force_research_payload = auto_handoff_payload

        if not request_body.session_id:
            title_seed = effective_user_input if effective_user_input != "/research" else "Research Request"
            await request.app.state.database.ensure_user_chat_session(
                user_id=current_user.id,
                session_id=session_id,
                topic=derive_session_title(title_seed),
            )
        else:
            await request.app.state.database.touch_user_session(
                user_id=current_user.id,
                session_id=session_id,
            )

        if should_set_pending_research:
            await request.app.state.database.set_user_session_pending_research(
                current_user.id,
                session_id,
                True,
            )
        elif should_clear_pending_research and request_body.session_id:
            await request.app.state.database.set_user_session_pending_research(
                current_user.id,
                session_id,
                False,
            )

        should_queue_research = bool(force_research_payload) and not ask_research_topic_only
        system_prompt = Nodes().chat_agent()
        user_message = HumanMessage(content=effective_user_input)
        await request.app.state.database.add_messages(session_id, [user_message])

        if should_queue_research:
            research_id = await request.app.state.database.enqueue_research_job(
                user_id=current_user.id,
                session_id=session_id,
                research_idea=str(force_research_payload or effective_user_input),
                model_tier=request_body.model,
                research_breadth=request_body.research_breadth,
                research_depth=request_body.research_depth,
                document_length=request_body.document_length,
            )
            await request.app.state.database.set_user_session_active_task(
                user_id=current_user.id,
                session_id=session_id,
                task={
                    "id": research_id,
                    "type": "research",
                    "status": "queued",
                },
            )
            return ChatResponse(
                session_id=session_id,
                research_id=research_id,
                status="queued",
            )

        state = {"messages": [user_message]}
        selected_chat_model = _resolve_chat_model(request, request_body.model)
        chat_agent = Agent(
            session_id=session_id,
            database=request.app.state.database,
            model=selected_chat_model,
            system_prompt=system_prompt,
            browser=request.app.state.browser,
            model_tier=request_body.model,
            research_breadth=request_body.research_breadth,
            research_depth=request_body.research_depth,
            document_length=request_body.document_length,
            force_research_payload=force_research_payload,
            ask_research_topic_only=ask_research_topic_only,
            allow_research_handoff=False,
        )
        result = await chat_agent.graph.ainvoke(state)
        final_document = result.get("final_document")
        try:
            final_document = final_document.as_str if final_document else None
        except Exception:
             pass
        if final_document:
            return ChatResponse(
                session_id=session_id,
                response=str(final_document),
                status="completed",
            )

        final_messages = result.get("messages", [])
        if not final_messages:
            raise Exception("No response from chat agent")
        response_text = str(
            getattr(final_messages[-1], "text", "")
            or getattr(final_messages[-1], "content", "")
            or ""
        ).strip()
        if not response_text:
            raise Exception("No text response from chat agent")
        return ChatResponse(
            session_id=session_id,
            response=response_text,
            status="completed",
        )
    except HTTPException:
        raise
    except Exception as error:
        print(f"/chat internal error: {error}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error.")
