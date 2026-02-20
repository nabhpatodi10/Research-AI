import asyncio
from datetime import datetime, timezone


class DatabaseFeedbackMixin:
    async def add_feedback(
        self,
        user_id: str,
        user_email: str,
        feedback_type: str,
        satisfaction: str,
        comments: str,
    ) -> None:
        await asyncio.to_thread(
            self._add_feedback_sync,
            user_id,
            user_email,
            feedback_type,
            satisfaction,
            comments,
        )

    def _add_feedback_sync(
        self,
        user_id: str,
        user_email: str,
        feedback_type: str,
        satisfaction: str,
        comments: str,
    ) -> None:
        self._firestore_client.collection("feedback").add(
            {
                "userId": user_id,
                "userEmail": user_email,
                "feedbackType": feedback_type,
                "satisfaction": satisfaction,
                "comments": comments,
                "createdAt": datetime.now(timezone.utc),
            }
        )
