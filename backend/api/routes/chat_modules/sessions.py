import logging

import uuid_utils
from fastapi import APIRouter, Depends, HTTPException, Request

from api.models import (
    ChatMessage,
    ChatMessagesResponse,
    ChatSession,
    ChatSessionsResponse,
    OkResponse,
    RenameSessionRequest,
    SessionMutationResponse,
    SessionTask,
    SessionUser,
    ShareSessionRequest,
    ShareSessionResponse,
)
from api.routes.chat_modules.common import get_active_research_task
from api.session import get_current_user
from api.utils import normalize_email


router = APIRouter()
logger = logging.getLogger(__name__)


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
    active_task = await get_active_research_task(
        request=request,
        user_id=current_user.id,
        session_id=session_id,
    )
    return ChatMessagesResponse(
        messages=[ChatMessage(**message) for message in messages],
        active_task=(SessionTask(**active_task) if active_task else None),
    )


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


@router.post("/chat/sessions/{session_id}/share", response_model=ShareSessionResponse)
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

    if payload.collaborative:
        await request.app.state.database.share_session_to_user(
            from_user_id=current_user.id,
            to_user_id=target_user["id"],
            session_id=session_id,
            topic=session["topic"],
            shared_by_email=current_user.email,
            share_mode="collaborative",
            source_session_id=None,
        )
        return ShareSessionResponse(
            ok=True,
            mode="collaborative",
            shared_session_id=session_id,
        )

    copied_session_id = str(uuid_utils.uuid7())
    copied_session_shared = False
    try:
        source_messages = await request.app.state.database.get_messages(session_id)
        if source_messages:
            await request.app.state.database.add_messages(copied_session_id, source_messages)

        await request.app.state.database.share_session_to_user(
            from_user_id=current_user.id,
            to_user_id=target_user["id"],
            session_id=copied_session_id,
            topic=session["topic"],
            shared_by_email=current_user.email,
            share_mode="snapshot",
            source_session_id=session_id,
        )
        copied_session_shared = True
    except Exception as error:
        logger.exception(
            "Failed to share snapshot session %s from %s to %s: %s",
            copied_session_id,
            session_id,
            target_user["id"],
            error,
        )
        try:
            await request.app.state.database.clear_chat(copied_session_id)
        except Exception:
            pass
        if copied_session_shared:
            try:
                await request.app.state.database.delete_user_session(
                    target_user["id"],
                    copied_session_id,
                )
            except Exception:
                pass
        raise HTTPException(status_code=500, detail="Failed to share chat snapshot.")

    return ShareSessionResponse(
        ok=True,
        mode="snapshot",
        shared_session_id=copied_session_id,
    )
