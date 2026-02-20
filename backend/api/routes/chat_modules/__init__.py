from fastapi import APIRouter

from .messages import router as messages_router
from .sessions import router as sessions_router
from .tasks import router as tasks_router


router = APIRouter(tags=["chat"])
router.include_router(sessions_router)
router.include_router(tasks_router)
router.include_router(messages_router)

__all__ = ["router"]
