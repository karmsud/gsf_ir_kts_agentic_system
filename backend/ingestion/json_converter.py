"""
JSON converter for reference catalogs (error codes, API specs, etc.)
Converts structured JSON to normalized text for indexing.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.common.doc_types import normalize_doc_type, REFERENCE


def convert_json(path: str) -> tuple[str, list[str]]:
    """
    Convert JSON reference catalogs to indexable text.
    
    Expected structure:
    {
      "tool_name": [
        {"code": "ERR-XXX-000", "message": "...", "category": "...", "severity": "..."},
        ...
      ]
    }
    
    Returns:
        (normalized_text, image_refs)
    """
    file_path = Path(path)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON: {e}")
    
    # Build normalized text for indexing
    lines = []
    
    # Add title based on filename
    title = file_path.stem.replace('_', ' ').title()
    lines.append(f"# {title}\n")
    lines.append("This is a reference catalog for error codes and diagnostics.\n")
    
    # Process each tool/category
    for tool_name, entries in data.items():
        if not isinstance(entries, list):
            continue
            
        lines.append(f"\n## {tool_name.upper()} Error Codes\n")
        
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            
            code = entry.get('code', 'UNKNOWN')
            message = entry.get('message', '')
            category = entry.get('category', '')
            severity = entry.get('severity', '')
            
            # Format: CODE: message (Category: X, Severity: Y)
            # This ensures both code token and context are in the chunk
            entry_text = f"**{code}**: {message}"
            
            metadata_parts = []
            if category:
                metadata_parts.append(f"Category: {category}")
            if severity:
                metadata_parts.append(f"Severity: {severity}")
            
            if metadata_parts:
                entry_text += f" ({', '.join(metadata_parts)})"
            
            lines.append(f"- {entry_text}\n")
    
    # Extract all error codes for metadata
    all_codes = []
    for tool_name, entries in data.items():
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and 'code' in entry:
                    all_codes.append(entry['code'])
    
    # Add searchable footer with all codes (helps with "list all error codes" queries)
    if all_codes:
        lines.append("\n## Complete Error Code List\n")
        lines.append(f"This catalog contains the following error codes: {', '.join(all_codes)}\n")
    
    normalized_text = ''.join(lines)
    
    # No images in JSON
    return normalized_text, []


def extract_json_metadata(path: str) -> dict:
    """
    Extract metadata from JSON reference catalog.
    
    Returns:
        {
            "doc_type": normalize_doc_type(REFERENCE),
            "tool_names": ["toolx", "tooly"],
            "error_codes": ["ERR-AUTH-401", "ERR-UPL-013", ...],
            "categories": ["Auth", "Policy", ...],
        }
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {"doc_type": normalize_doc_type(REFERENCE), "tool_names": [], "error_codes": [], "categories": []}
    
    tool_names = list(data.keys())
    error_codes = []
    categories = set()
    
    for tool_name, entries in data.items():
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    if 'code' in entry:
                        error_codes.append(entry['code'])
                    if 'category' in entry:
                        categories.add(entry['category'])
    
    return {
        "doc_type": normalize_doc_type(REFERENCE),
        "tool_names": tool_names,
        "error_codes": error_codes,
        "categories": sorted(categories),
    }
