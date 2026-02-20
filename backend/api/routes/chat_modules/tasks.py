from fastapi import APIRouter, Depends, HTTPException, Request

from api.models import SessionUser, TaskStatusResponse
from api.routes.chat_modules.common import normalize_research_status
from api.session import get_current_user
from research_progress import normalize_research_node


router = APIRouter()


@router.get("/chat/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    request: Request,
    current_user: SessionUser = Depends(get_current_user),
):
    job = await request.app.state.database.get_research_job(task_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    session_id = str(job.get("sessionId") or "").strip()
    if not session_id:
        raise HTTPException(status_code=404, detail="Task not found.")
    has_access = await request.app.state.database.user_has_session(current_user.id, session_id)
    if not has_access:
        raise HTTPException(status_code=404, detail="Task not found.")

    status = normalize_research_status(str(job.get("status") or ""))
    result_text = str(job.get("resultText") or "").strip()
    error_message = str(job.get("error") or "").strip() or None
    if status in {"completed", "failed"}:
        await request.app.state.database.clear_user_session_active_task_if_matches(
            user_id=current_user.id,
            session_id=session_id,
            task_id=task_id,
        )
    if status != "completed":
        result_text = ""

    return TaskStatusResponse(
        id=task_id,
        type="research",
        status=status,
        session_id=session_id,
        current_node=normalize_research_node(job.get("currentNode")),
        progress_message=(str(job.get("progressMessage") or "").strip() or None),
        result=result_text or None,
        error=error_message,
    )
