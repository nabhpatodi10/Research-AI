from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class DatabaseMessagesMixin:
    async def add_messages(self, session_id: str, message: BaseMessage | list[BaseMessage]) -> None:
        chat = await self.chat(session_id=session_id)
        if isinstance(message, list):
            return await chat.aadd_messages(message)
        return await chat.aadd_messages([message])

    async def get_messages(self, session_id: str) -> list[BaseMessage]:
        chat = await self.chat(session_id=session_id)
        return await chat.aget_messages()

    async def clear_chat(self, session_id: str) -> None:
        chat = await self.chat(session_id=session_id)
        await chat.aclear()
        await self.clear_vector_store(session_id=session_id)

    @classmethod
    def _message_text(cls, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") == "text" and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif isinstance(item.get("content"), str):
                        parts.append(item["content"])
            return "\n".join(part for part in parts if part.strip())
        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                return content["text"]
            if isinstance(content.get("content"), str):
                return content["content"]
            return str(content)
        return str(content or "")

    async def get_session_messages_for_ui(self, session_id: str) -> list[dict[str, str]]:
        messages = await self.get_messages(session_id)
        ui_messages: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            sender = None
            if isinstance(message, HumanMessage):
                sender = "user"
            elif isinstance(message, AIMessage):
                sender = "ai"
            if sender is None:
                continue

            text = self._message_text(getattr(message, "content", "")).strip()
            if not text:
                continue

            ui_messages.append({"id": f"msg-{index}", "sender": sender, "text": text})
        return ui_messages
