"""CSV incident log converter with aggregation"""
from __future__ import annotations

import csv
from pathlib import Path
from collections import Counter
from datetime import datetime


def convert_csv(path: str) -> tuple[str, list[str]]:
    """
    Convert CSV to normalized text with aggregated summary.
    
    Creates:
    1. Aggregated summary (top error codes, affected tools, counts)
    2. Sample rows (first N rows for context)
    
    Returns searchable text optimized for incident/log queries.
    """
    file_path = Path(path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    if not rows:
        return f"Empty CSV file: {file_path.name}", []
    
    # Extract headers
    headers = rows[0].keys() if rows else []
    
    # Aggregate statistics
    error_code_col = None
    tool_col = None
    date_col = None
    
    # Detect common column names (case-insensitive)
    for col in headers:
        col_lower = col.lower()
        if 'error' in col_lower and 'code' in col_lower:
            error_code_col = col
        elif 'tool' in col_lower or 'platform' in col_lower or 'app' in col_lower:
            tool_col = col
        elif 'date' in col_lower or 'time' in col_lower:
            date_col = col
    
    # Build aggregated summary
    text_parts = [
        f"Incident Log: {file_path.name}",
        f"Format: CSV",
        f"Total Records: {len(rows)}",
        f"Columns: {', '.join(headers)}",
        "",
        "=== AGGREGATED SUMMARY ===",
        ""
    ]
    
    if error_code_col:
        error_counts = Counter(row.get(error_code_col, 'UNKNOWN') for row in rows)
        text_parts.append("Top Error Codes by Count:")
        for code, count in error_counts.most_common(10):
            text_parts.append(f"  - {code}: {count} occurrences")
        text_parts.append("")
    
    if tool_col:
        tool_counts = Counter(row.get(tool_col, 'UNKNOWN') for row in rows)
        text_parts.append("Affected Tools/Platforms:")
        for tool, count in tool_counts.most_common(5):
            text_parts.append(f"  - {tool}: {count} incidents")
        text_parts.append("")
    
    if date_col:
        dates = [row.get(date_col, '') for row in rows if row.get(date_col)]
        if dates:
            text_parts.append(f"Date Range: {min(dates)} to {max(dates)}")
            text_parts.append(f"Most Recent: {max(dates)}")
            text_parts.append("")
    
    # Add sample rows (first 10 rows, truncated for readability)
    text_parts.append("=== SAMPLE ROWS (First 10) ===")
    text_parts.append("")
    
    max_sample_rows = min(10, len(rows))
    for i, row in enumerate(rows[:max_sample_rows], 1):
        text_parts.append(f"Row {i}:")
        for key, value in row.items():
            # Truncate long values to keep chunk size reasonable
            value_str = str(value)[:100]
            text_parts.append(f"  {key}: {value_str}")
        text_parts.append("")
    
    if len(rows) > max_sample_rows:
        text_parts.append(f"... and {len(rows) - max_sample_rows} more rows")
    
    # Add searchable keywords section
    text_parts.append("")
    text_parts.append("=== SEARCHABLE KEYWORDS ===")
    text_parts.append(f"CSV file: {file_path.name}")
    text_parts.append(f"Record count: {len(rows)}")
    if error_code_col:
        all_errors = set(row.get(error_code_col, '') for row in rows if row.get(error_code_col))
        text_parts.append(f"Error codes present: {', '.join(sorted(all_errors))}")
    
    return "\n".join(text_parts), []
