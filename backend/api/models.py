from typing import Literal

from pydantic import BaseModel


class SessionUser(BaseModel):
    id: str
    email: str
    name: str
    provider: str


class AuthResponse(BaseModel):
    user: SessionUser


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class MeResponse(BaseModel):
    user: SessionUser


class LogoutResponse(BaseModel):
    ok: bool


class ChatRequest(BaseModel):
    session_id: str | None = None
    user_input: str
    force_research: bool = False
    model: Literal["mini", "pro"] = "pro"
    research_breadth: Literal["low", "medium", "high"] = "medium"
    research_depth: Literal["low", "medium", "high"] = "high"
    document_length: Literal["low", "medium", "high"] = "high"


class ChatSession(BaseModel):
    id: str
    topic: str
    createdAt: str
    isShared: bool
    sharedBy: str | None = None
    shareMode: Literal["collaborative", "snapshot"] | None = None
    sourceSessionId: str | None = None


class ChatSessionsResponse(BaseModel):
    sessions: list[ChatSession]


class ChatMessage(BaseModel):
    id: str
    sender: Literal["user", "ai"]
    text: str


class SessionTask(BaseModel):
    id: str
    type: Literal["research"]
    status: Literal["queued", "running", "completed", "failed"]
    current_node: str | None = None
    progress_message: str | None = None


class ChatMessagesResponse(BaseModel):
    messages: list[ChatMessage]
    active_task: SessionTask | None = None


class ChatResponseMessage(BaseModel):
    kind: Literal["message"] = "message"
    session_id: str
    message: ChatMessage


class ChatResponseTask(BaseModel):
    kind: Literal["task"] = "task"
    session_id: str
    task: SessionTask


ChatResponse = ChatResponseMessage | ChatResponseTask


class RenameSessionRequest(BaseModel):
    topic: str


class ShareSessionRequest(BaseModel):
    email: str
    collaborative: bool = True


class ShareSessionResponse(BaseModel):
    ok: bool
    mode: Literal["collaborative", "snapshot"]
    shared_session_id: str


class SessionMutationResponse(BaseModel):
    ok: bool
    session: ChatSession | None = None


class OkResponse(BaseModel):
    ok: bool


class FeedbackRequest(BaseModel):
    feedbackType: str
    satisfaction: str
    comments: str


class TaskStatusResponse(BaseModel):
    id: str
    type: Literal["research"]
    status: Literal["queued", "running", "completed", "failed"]
    session_id: str
    current_node: str | None = None
    progress_message: str | None = None
    result: str | None = None
    error: str | None = None
