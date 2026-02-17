from __future__ import annotations

import re


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """
    Semantic chunking using recursive separators to preserve sentence boundaries.
    Logic: Split by Paragraph -> Sentence -> Word -> Char.
    """
    if not text:
        return []

    separators = ["\n\n", "\n", ". ", " ", ""]
    
    def _split_on_separator(text: str, separator: str) -> list[str]:
        if separator == "":
            return list(text)
        return [s for s in text.split(separator) if s]

    def _merge_splits(splits: list[str], separator: str) -> list[str]:
        docs = []
        current_doc = []
        total = 0
        separator_len = len(separator)
        
        for d in splits:
            _len = len(d)
            if total + _len + (separator_len if current_doc else 0) > chunk_size:
                if total > chunk_size: # Edge case: single chunk too big
                     pass 
                if current_doc:
                    doc = separator.join(current_doc)
                    if doc.strip():
                        docs.append(doc)
                    
                    # Handle overlap by keeping tail elements
                    while total > chunk_overlap and current_doc:
                         total -= len(current_doc[0]) + separator_len
                         current_doc.pop(0)
                         
                if not current_doc:
                    total = 0
                    
            current_doc.append(d)
            total += _len + (separator_len if len(current_doc) > 1 else 0)
            
        if current_doc:
            doc = separator.join(current_doc)
            if doc.strip():
                docs.append(doc)
        return docs

    def _recursive_split(text: str, separators: list[str]) -> list[str]:
        final_chunks = []
        separator = separators[-1]
        new_separators = []
        
        # Find appropriate separator
        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break
        
        splits = _split_on_separator(text, separator)
        
        good_splits = []
        for s in splits:
            if len(s) < chunk_size:
                good_splits.append(s)
            else:
                if new_separators:
                    good_splits.extend(_recursive_split(s, new_separators))
                else:
                    good_splits.append(s)
                    
        return _merge_splits(good_splits, separator)

    return _recursive_split(text, separators)
