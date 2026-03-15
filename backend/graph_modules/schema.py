from typing import Dict, List, TypedDict

from structures import CompleteDocument, ContentSection, Outline, Perspectives


class ExpertSectionProgress(TypedDict):
    status: str
    content: str


class ExpertProgressEntry(TypedDict, total=False):
    expert_name: str
    summary: str
    section_results: List[ExpertSectionProgress]


class ExpertProgressState(TypedDict, total=False):
    experts: Dict[str, ExpertProgressEntry]


class FinalSectionProgressState(TypedDict, total=False):
    summary: str
    completed_sections: List[ContentSection]


class graphSchema(TypedDict, total=False):
    research_idea: str
    document_outline: Outline
    perspectives: Perspectives
    perspective_content: List[List[str]]
    final_document: CompleteDocument
    expert_progress: ExpertProgressState
    final_section_progress: FinalSectionProgressState
