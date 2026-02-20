from io import BytesIO


def extract_pdf_text_from_bytes(pdf_bytes: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    pages: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        normalized = page_text.strip()
        if normalized:
            pages.append(normalized)
    return "\n\n".join(pages).strip(), len(reader.pages)


def to_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def to_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
