import os
from datetime import datetime, timezone
from typing import Any

from google.cloud.firestore import Client
from langchain_google_firestore import FirestoreChatMessageHistory, FirestoreVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from settings import get_settings


class DatabaseCommonMixin:
    def __init__(self):
        settings = get_settings()
        project_id = settings.google_project_id or settings.google_cloud_project
        if project_id and not settings.google_cloud_project:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id

        credentials_path = settings.google_application_credentials
        if credentials_path and not os.path.isabs(credentials_path):
            backend_root = os.path.dirname(os.path.dirname(__file__))
            resolved_credentials_path = os.path.abspath(
                os.path.join(backend_root, credentials_path)
            )
            if os.path.exists(resolved_credentials_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = resolved_credentials_path

        self._firestore_client = Client(project=project_id)
        self._embedding_model = GoogleGenerativeAIEmbeddings(
            model="text-embedding-005",
            vertexai=True,
            project=project_id,
            location=settings.google_cloud_location,
        )
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.vector_split_chunk_size,
            chunk_overlap=settings.vector_split_chunk_overlap,
        )

    async def chat(self, session_id: str) -> FirestoreChatMessageHistory:
        return FirestoreChatMessageHistory(
            session_id=session_id,
            collection="chats",
            client=self._firestore_client,
            encode_message=False,
        )

    async def vector_store(self) -> FirestoreVectorStore:
        vector_store = FirestoreVectorStore(
            collection="vector",
            embedding_service=self._embedding_model,
            client=self._firestore_client,
        )
        return vector_store

    @staticmethod
    def _as_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if hasattr(value, "to_datetime"):
            converted = value.to_datetime()
            if isinstance(converted, datetime):
                if converted.tzinfo is None:
                    return converted.replace(tzinfo=timezone.utc)
                return converted
        return None

    @classmethod
    def _datetime_iso(cls, value: Any) -> str:
        dt = cls._as_datetime(value) or datetime.now(timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    @classmethod
    def _datetime_iso_optional(cls, value: Any) -> str | None:
        dt = cls._as_datetime(value)
        if dt is None:
            return None
        return dt.astimezone(timezone.utc).isoformat()

    def close_connection(self) -> None:
        self._firestore_client.close()
