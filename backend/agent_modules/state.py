import operator
from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import BaseMessage


class AgentExecutionState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    chat_history: NotRequired[list[BaseMessage]]
    research_idea: NotRequired[str]
    final_document: NotRequired[str]
