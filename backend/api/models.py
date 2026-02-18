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


class ChatResponse(BaseModel):
    session_id: str
    response: str


class ChatSession(BaseModel):
    id: str
    topic: str
    createdAt: str
    isShared: bool
    sharedBy: str | None = None


class ChatSessionsResponse(BaseModel):
    sessions: list[ChatSession]


class ChatMessage(BaseModel):
    id: str
    sender: Literal["user", "ai"]
    text: str


class ChatMessagesResponse(BaseModel):
    messages: list[ChatMessage]


class RenameSessionRequest(BaseModel):
    topic: str


class ShareSessionRequest(BaseModel):
    email: str


class SessionMutationResponse(BaseModel):
    ok: bool
    session: ChatSession | None = None


class OkResponse(BaseModel):
    ok: bool


class FeedbackRequest(BaseModel):
    feedbackType: str
    satisfaction: str
    comments: str
