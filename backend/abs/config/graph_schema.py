"""
ABS graph schema — node and edge type definitions for ABS domain.

Registers 10 ABS-specific node types and 10 edge types into
KTS's EnhancedGraphBuilder type system.  All prefixed with 'abs_'
to prevent namespace collisions with KTS's 14 standard types.
"""

from dataclasses import dataclass, field


@dataclass
class NodeTypeDef:
    """Definition of a graph node type."""
    name: str
    description: str
    properties: list[str] = field(default_factory=list)
    is_root: bool = False


@dataclass
class EdgeTypeDef:
    """Definition of a graph edge type."""
    name: str
    from_type: str
    to_type: str
    weight: float = 1.0


ABS_NODE_TYPES = [
    NodeTypeDef(
        name="abs_deal",
        description="ABS deal entity (e.g., Bear Stearns 2006-HE1)",
        properties=["deal_id", "issuer", "series", "closing_date", "deal_type"],
        is_root=True,
    ),
    NodeTypeDef(
        name="abs_document",
        description="Legal document (PSA, Indenture, Supplement)",
        properties=["doc_type", "content_hash", "filename", "page_count"],
    ),
    NodeTypeDef(
        name="abs_article",
        description="Article within a legal document",
        properties=["article_num", "title", "text_preview"],
    ),
    NodeTypeDef(
        name="abs_section",
        description="Section within an article",
        properties=["section_num", "parent_article", "title"],
    ),
    NodeTypeDef(
        name="abs_definition",
        description="Defined term within the agreement",
        properties=["term", "full_text", "section_ref"],
    ),
    NodeTypeDef(
        name="abs_obligation",
        description="Obligation or duty",
        properties=["actor", "verb", "full_text", "section_ref"],
    ),
    NodeTypeDef(
        name="abs_waterfall_rule",
        description="Payment waterfall priority rule",
        properties=["priority", "payee", "formula", "conditions"],
    ),
    NodeTypeDef(
        name="abs_class",
        description="Certificate/note class",
        properties=["class_name", "initial_balance", "rate_type", "coupon"],
    ),
    NodeTypeDef(
        name="abs_account",
        description="Deal account",
        properties=["account_name", "purpose", "section_ref"],
    ),
    NodeTypeDef(
        name="abs_trigger",
        description="Performance trigger or event of default",
        properties=["trigger_type", "threshold", "consequence", "section_ref"],
    ),
]

ABS_EDGE_TYPES = [
    EdgeTypeDef("HAS_DOCUMENT", "abs_deal", "abs_document", weight=1.0),
    EdgeTypeDef("HAS_ARTICLE", "abs_document", "abs_article", weight=1.0),
    EdgeTypeDef("HAS_SECTION", "abs_article", "abs_section", weight=1.0),
    EdgeTypeDef("DEFINES", "abs_section", "abs_definition", weight=0.9),
    EdgeTypeDef("HAS_OBLIGATION", "abs_section", "abs_obligation", weight=0.9),
    EdgeTypeDef("HAS_RULE", "abs_section", "abs_waterfall_rule", weight=0.95),
    EdgeTypeDef("REFERENCES", "abs_section", "abs_section", weight=0.7),
    EdgeTypeDef("USES_TERM", "abs_obligation", "abs_definition", weight=0.8),
    EdgeTypeDef("APPLIES_TO", "abs_waterfall_rule", "abs_class", weight=0.9),
    EdgeTypeDef("TRIGGERS", "abs_trigger", "abs_waterfall_rule", weight=0.85),
]


def get_all_node_type_names() -> list[str]:
    """Return all ABS node type names."""
    return [n.name for n in ABS_NODE_TYPES]


def get_all_edge_type_names() -> list[str]:
    """Return all ABS edge type names."""
    return [e.name for e in ABS_EDGE_TYPES]
