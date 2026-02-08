from typing import List, Optional, TypedDict, Annotated
from pydantic import BaseModel, Field
import operator
from langchain.messages import AnyMessage

class OutlineSubsection(BaseModel):
    subsection_title: str = Field(title="Title of the subsection")
    description: str = Field(title="Description of the content for the subsection")

    @property
    def as_str(self) -> str:
        return f"### {self.subsection_title}\n\n{self.description}".strip()


class OutlineSection(BaseModel):
    section_title: str = Field(title="Title of the section")
    description: str = Field(title="Description of the content for the section")
    subsections: Optional[List[OutlineSubsection]] = Field(
        default=None,
        title="Titles and descriptions for each subsection of the Research Document.",
    )

    @property
    def as_str(self) -> str:
        subsections = "\n\n".join(subsection.as_str for subsection in self.subsections) if self.subsections else ""
        return f"## {self.section_title}\n\n{self.description}\n\n{subsections}".strip()


class Outline(BaseModel):
    document_title: str = Field(title="Title of the Research Document")
    document_description: str = Field(title="Detailed description of the Research Document's focus and scope.")
    sections: List[OutlineSection] = Field(
        default_factory=list,
        title="Titles and descriptions for each section of the Research Document.",
    )

    @property
    def as_str(self) -> str:
        sections = "\n\n".join(section.as_str for section in self.sections)
        return f"# {self.document_title}\n\n## Research Document Description\n{self.document_description}\n\n{sections}".strip()

class Expert(BaseModel):
    name: str = Field(
        description="Name of the expert."
    )
    profession: str = Field(
        description="Profession of the expert which would help in understanding the perspective and point of view of the expert and also would help in understanding the relevance of the expert to the research topic.",
    )
    role: str = Field(
        description="Expert's role for the given research project, including their focus, concerns, motives, ideologies, etc.",
    )

    @property
    def as_str(self) -> str:
        return f"Name: {self.name}\nProfession: {self.profession}\nRole: {self.role}\n"


class Perspectives(BaseModel):
    experts: List[Expert] = Field(
        description="Comprehensive list of experts with their roles and affiliations."
    )

class ContentSection(BaseModel):
    section_title: str = Field(title="Title of the section")
    content: str = Field(title="Full content of the section")
    citations: List[str] = Field(default_factory=list, description="List of citations for the content")

    @property
    def as_str(self) -> str:
        citations = [
            str(citation).strip()
            for citation in (self.citations or [])
            if str(citation).strip()
        ]
        citation_block = "\n".join([f"[{i}] {cit}" for i, cit in enumerate(citations, start=1)])
        body = f"## {self.section_title}\n\n{self.content}".strip().strip("#").strip("#").strip()
        if not citation_block:
            return body
        return f"{body}\n\n{citation_block}".strip()

class CompleteDocument(BaseModel):
    title: str = Field(title="Title of the document")
    sections: List[ContentSection] = Field(
        default_factory=list,
        title="Sections of the document",
    )

    @property
    def as_str(self) -> str:
        sections = [
            f"## {section.section_title}\n\n{section.content}".strip()
            for section in (self.sections or [])
        ]
        sections_block = "\n\n".join(sections).strip() or "No sections generated."

        references: list[str] = []
        seen: set[str] = set()
        for section in (self.sections or []):
            for citation in (section.citations or []):
                citation_text = str(citation).strip()
                if not citation_text or citation_text in seen:
                    continue
                seen.add(citation_text)
                references.append(citation_text)

        references_block = (
            "\n".join([f"[{i}] {citation}" for i, citation in enumerate(references, start=1)])
            if references
            else "No references provided."
        )

        return f"# {self.title}\n\n{sections_block}\n\n## References\n{references_block}".strip()
    
class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]
