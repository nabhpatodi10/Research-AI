import uuid_utils
from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.messages import HumanMessage

from agent import Agent
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
        if request_body.session_id:
            has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
            if not has_access:
                raise HTTPException(status_code=403, detail="You do not have access to this chat session.")
        else:
            await request.app.state.database.ensure_user_chat_session(
                user_id=current_user.id,
                session_id=session_id,
                topic=derive_session_title(request_body.user_input),
            )

        system_prompt = Nodes().chat_agent()
        user_message = HumanMessage(content=request_body.user_input)
        await request.app.state.database.add_messages(session_id, [user_message])
        state = {"messages": [user_message]}
        chat_agent = Agent(
            session_id=session_id,
            database=request.app.state.database,
            model=request.app.state.chat_model,
            system_prompt=system_prompt,
            browser=request.app.state.browser,
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
        print(error)
        raise HTTPException(status_code=500, detail=str(error))
