from fastapi import APIRouter, Depends, HTTPException, Request

from api.models import FeedbackRequest, OkResponse, SessionUser
from api.session import get_current_user


router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=OkResponse)
async def submit_feedback(
    payload: FeedbackRequest, request: Request, current_user: SessionUser = Depends(get_current_user)
):
    comments = payload.comments.strip()
    satisfaction = payload.satisfaction.strip()
    feedback_type = payload.feedbackType.strip() or "General Feedback"
    if not comments or not satisfaction:
        raise HTTPException(status_code=400, detail="Satisfaction and comments are required.")

    await request.app.state.database.add_feedback(
        user_id=current_user.id,
        user_email=current_user.email,
        feedback_type=feedback_type,
        satisfaction=satisfaction,
        comments=comments,
    )
    return OkResponse(ok=True)

