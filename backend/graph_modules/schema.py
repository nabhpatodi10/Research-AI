from typing import List, TypedDict

from structures import CompleteDocument, Outline, Perspectives


class graphSchema(TypedDict):
    research_idea: str
    document_outline: Outline
    perspectives: Perspectives
    perspective_content: List[List[str]]
    final_document: CompleteDocument
