"""YAML/INI configuration file converter"""
from __future__ import annotations

from pathlib import Path


def convert_yaml(path: str) -> tuple[str, list[str]]:
    """
    Convert YAML to normalized text format.
    
    Preserves key/value structure for searchability.
    """
    try:
        import yaml
    except ImportError:
        raise RuntimeError("PyYAML is required for YAML conversion. Install with: pip install pyyaml")
    
    file_path = Path(path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    # Convert to searchable text format
    text_parts = [
        f"Configuration File: {file_path.name}",
        f"Format: YAML",
        "",
        "Configuration Settings:",
        ""
    ]
    
    def flatten_dict(d, prefix=''):
        """Recursively flatten nested YAML structure"""
        lines = []
        if isinstance(d, dict):
            for key, value in d.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, (dict, list)):
                    lines.append(f"{full_key}:")
                    lines.extend(flatten_dict(value, full_key))
                else:
                    lines.append(f"{full_key}: {value}")
        elif isinstance(d, list):
            for i, item in enumerate(d):
                lines.extend(flatten_dict(item, f"{prefix}[{i}]"))
        else:
            lines.append(f"{prefix}: {d}")
        return lines
    
    text_parts.extend(flatten_dict(data))
    
    return "\n".join(text_parts), []


def convert_ini(path: str) -> tuple[str, list[str]]:
    """
    Convert INI to normalized text format.
    
    Preserves section/key/value structure for searchability.
    """
    import configparser
    
    file_path = Path(path)
    
    config = configparser.ConfigParser()
    config.read(file_path, encoding='utf-8')
    
    # Convert to searchable text format
    text_parts = [
        f"Configuration File: {file_path.name}",
        f"Format: INI",
        "",
        "Configuration Settings:",
        ""
    ]
    
    for section in config.sections():
        text_parts.append(f"[{section}]")
        for key, value in config.items(section):
            text_parts.append(f"{key}: {value}")
        text_parts.append("")  # Blank line between sections
    
    return "\n".join(text_parts), []
