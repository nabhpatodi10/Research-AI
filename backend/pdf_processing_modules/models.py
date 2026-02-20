from dataclasses import dataclass


@dataclass(slots=True)
class PdfProcessResult:
    status: str
    text: str
    title: str
    source: str
    partial: bool = False
    total_pages: int = 0
    error: str = ""
