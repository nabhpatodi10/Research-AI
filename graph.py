from dotenv import load_dotenv
load_dotenv()

from typing import TypedDict, Annotated, List, Optional
from pydantic import BaseModel, Field
import operator
from langchain_core.messages import AnyMessage
from langgraph.graph import StateGraph, END
from langchain_core.documents import Document

from langchain_groq import ChatGroq

from tools import tools
from nodes import Nodes

class Subsection(BaseModel):
    subsection_title: str = Field(..., title="Title of the subsection")
    description: str = Field(..., title="Content of the subsection")

    @property
    def as_str(self) -> str:
        return f"### {self.subsection_title}\n\n{self.description}".strip()


class Section(BaseModel):
    section_title: str = Field(..., title="Title of the section")
    description: str = Field(..., title="Content of the section")
    subsections: Optional[List[Subsection]] = Field(
        default=None,
        title="Titles and descriptions for each subsection of the Wikipedia page.",
    )

    @property
    def as_str(self) -> str:
        subsections = "\n\n".join(
            f"### {subsection.subsection_title}\n\n{subsection.description}"
            for subsection in self.subsections or []
        )
        return f"## {self.section_title}\n\n{self.description}\n\n{subsections}".strip()


class Outline(BaseModel):
    page_title: str = Field(..., title="Title of the Wikipedia page")
    sections: List[Section] = Field(
        default_factory=list,
        title="Titles and descriptions for each section of the Wikipedia page.",
    )

    @property
    def as_str(self) -> str:
        sections = "\n\n".join(section.as_str for section in self.sections)
        return f"# {self.page_title}\n\n{sections}".strip()
    
class Related_Topics(BaseModel):
    topics: List[str] = Field(
        default_factory=list,
        title="List of related topics."
    )

class GraphSchema(TypedDict):
    topic: str
    output_format: str
    outline: str
    covered: str
    search_topics: List[str]

model = ChatGroq(model = "llama-3.3-70b-versatile")

# outline = model.with_structured_output(Outline).invoke(Nodes().generate_outline("Text Extraction and Recognition Algorithms", "professional report"))

# print(outline.as_str)

related_topics = model.with_structured_output(Related_Topics).invoke(Nodes().get_related_topics("Text Extraction and Recognition Algorithms"))

print(related_topics.topics)