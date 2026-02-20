import logging

import uuid_utils
from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.messages import HumanMessage

from agent import Agent, build_research_handoff_context
from api.models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatResponseMessage,
    ChatResponseTask,
    SessionTask,
    SessionUser,
)
from api.routes.chat_modules.common import (
    get_active_research_task,
    maybe_auto_research_handoff_payload,
    parse_research_command,
    resolve_chat_model,
)
from api.session import get_current_user
from api.utils import derive_session_title
from nodes import Nodes
from research_progress import progress_message_for_node


router = APIRouter()
logger = logging.getLogger(__name__)


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
        is_research_command, command_topic = parse_research_command(raw_user_input)
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
            active_task = await get_active_research_task(
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
            auto_handoff_payload = await maybe_auto_research_handoff_payload(
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
            session_active_task = await get_active_research_task(
                request=request,
                user_id=current_user.id,
                session_id=session_id,
            )
            if session_active_task is not None:
                raise HTTPException(
                    status_code=409,
                    detail="A research task is already running for this session. Wait for it to finish.",
                )

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
                    "current_node": "queued",
                    "progress_message": progress_message_for_node("queued"),
                },
            )
            return ChatResponseTask(
                kind="task",
                session_id=session_id,
                task=SessionTask(
                    id=research_id,
                    type="research",
                    status="queued",
                    current_node="queued",
                    progress_message=progress_message_for_node("queued"),
                ),
            )

        state = {"messages": [user_message]}
        selected_chat_model = resolve_chat_model(request, request_body.model)
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
            return ChatResponseMessage(
                kind="message",
                session_id=session_id,
                message=ChatMessage(
                    id=f"msg-{uuid_utils.uuid7()}",
                    sender="ai",
                    text=str(final_document),
                ),
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
        return ChatResponseMessage(
            kind="message",
            session_id=session_id,
            message=ChatMessage(
                id=f"msg-{uuid_utils.uuid7()}",
                sender="ai",
                text=response_text,
            ),
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("/chat internal error: %s", error)
        raise HTTPException(status_code=500, detail="Internal server error.")
