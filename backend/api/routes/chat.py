import uuid_utils
import re
import traceback
from fastapi import APIRouter, Depends, HTTPException, Request
from langchain.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from agent import Agent, build_research_handoff_context
from api.models import (
    ChatMessage,
    ChatMessagesResponse,
    ChatRequest,
    ChatResponse,
    ChatSession,
    ChatSessionsResponse,
    OkResponse,
    RenameSessionRequest,
    SessionMutationResponse,
    SessionUser,
    ShareSessionRequest,
)
from api.session import get_current_user
from api.utils import derive_session_title, normalize_email
from nodes import Nodes


router = APIRouter(tags=["chat"])

RESEARCH_COMMAND_PATTERN = re.compile(r"^\s*/research(?:\s+(?P<topic>[\s\S]*))?$", re.IGNORECASE)


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

        system_prompt = Nodes().chat_agent()
        user_message = HumanMessage(content=effective_user_input)
        await request.app.state.database.add_messages(session_id, [user_message])
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
        )
        result = await chat_agent.graph.ainvoke(state)
        final_document = result.get("final_document")
        if final_document:
            return ChatResponse(session_id=session_id, response=str(final_document))

        final_messages = result.get("messages", [])
        if not final_messages:
            raise Exception("No response from chat agent")
        response_text = final_messages[-1].text
        return ChatResponse(session_id=session_id, response=response_text)
    except HTTPException:
        raise
    except Exception as error:
        print(f"/chat internal error: {error}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error.")
