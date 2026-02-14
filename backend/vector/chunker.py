from __future__ import annotations

from backend.common.models import TextChunk
from backend.common.text_utils import chunk_text


def chunk_document(doc_id: str, source_path: str, text: str, chunk_size: int, chunk_overlap: int) -> list[TextChunk]:
    chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [
        TextChunk(
            chunk_id=f"{doc_id}_chunk_{index}",
            doc_id=doc_id,
            content=chunk,
            source_path=source_path,
            chunk_index=index,
        )
        for index, chunk in enumerate(chunks)
    ]
