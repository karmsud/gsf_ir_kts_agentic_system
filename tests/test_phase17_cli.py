"""Phase 17 — CLI Integration tests (Step 9)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.main import cli  # The Click group


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_retrieval_result(extra: dict | None = None):
    """Build a fake AgentResult-like object returned by RetrievalService.execute."""
    data = {
        "search_result": {
            "context_chunks": [],
            "confidence": 0.85,
            "citations": [],
        },
    }
    if extra:
        data.update(extra)
    result = MagicMock()
    result.success = True
    result.data = data
    return result


def _mock_deal_list(deals: list[dict] | None = None):
    """Return a plausible DealCatalog mock."""
    if deals is None:
        deals = [
            {"slug": "fin_deal1", "deal_name": "Deal One", "vintage": 2005, "doc_count": 3, "status": "active"},
            {"slug": "fin_deal2", "deal_name": "Deal Two", "vintage": 2006, "doc_count": 5, "status": "active"},
        ]
    cat = MagicMock()
    cat.list_all_deals.return_value = deals
    cat.search_deals.return_value = [d for d in deals if "bear" in d["slug"]]
    return cat


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("cli.main.load_config")
@patch("cli.main.RetrievalService")
def test_cli_doc_filter_option_parsed(mock_rs_cls, mock_cfg):
    """--doc-filter PSA is forwarded without crash."""
    mock_cfg.return_value = MagicMock()
    mock_rs_cls.return_value.execute.return_value = _mock_retrieval_result()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "what is distribution date", "--doc-filter", "PSA"])

    assert result.exit_code == 0, result.output
    call_payload = mock_rs_cls.return_value.execute.call_args[0][0]
    assert call_payload["doc_name_prefix"] == "PSA"


@patch("cli.main.load_config")
@patch("cli.main.RetrievalService")
def test_cli_mode_option_parsed(mock_rs_cls, mock_cfg):
    """--mode compare is forwarded as phase17_mode."""
    mock_cfg.return_value = MagicMock()
    mock_rs_cls.return_value.execute.return_value = _mock_retrieval_result()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "waterfall", "--mode", "compare"])

    assert result.exit_code == 0, result.output
    call_payload = mock_rs_cls.return_value.execute.call_args[0][0]
    assert call_payload["phase17_mode"] == "compare"


@patch("cli.main.load_config")
@patch("cli.main.RetrievalService")
def test_cli_scopes_option_parsed(mock_rs_cls, mock_cfg):
    """--scopes fin_deal1,fin_deal2 produces a list."""
    mock_cfg.return_value = MagicMock()
    mock_rs_cls.return_value.execute.return_value = _mock_retrieval_result()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "q", "--scopes", "fin_deal1,fin_deal2"])

    assert result.exit_code == 0, result.output
    call_payload = mock_rs_cls.return_value.execute.call_args[0][0]
    assert call_payload["phase17_scopes"] == ["fin_deal1", "fin_deal2"]


@patch("cli.main.load_config")
@patch("cli.main.RetrievalService")
def test_cli_scopes_wildcard(mock_rs_cls, mock_cfg):
    """--scopes 'bear*' is passed through as a single-element list."""
    mock_cfg.return_value = MagicMock()
    mock_rs_cls.return_value.execute.return_value = _mock_retrieval_result()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "q", "--scopes", "bear*"])

    assert result.exit_code == 0, result.output
    call_payload = mock_rs_cls.return_value.execute.call_args[0][0]
    assert call_payload["phase17_scopes"] == ["bear*"]


@patch("cli.main.load_config")
def test_cli_list_deals_all(mock_cfg):
    """list-deals without filter returns all deals in table format."""
    mock_cfg.return_value = MagicMock()
    cat = _mock_deal_list()

    runner = CliRunner()
    with patch("backend.vector.deal_catalog.DealCatalog", return_value=cat):
        result = runner.invoke(cli, ["list-deals"])

    assert result.exit_code == 0, result.output
    # Table header is present
    assert "Slug" in result.output or "slug" in result.output.lower() or "Total:" in result.output


@patch("cli.main.load_config")
def test_cli_list_deals_filtered(mock_cfg):
    """list-deals --scope 'bear*' invokes search_deals with pattern."""
    mock_cfg.return_value = MagicMock()
    cat = _mock_deal_list([
        {"slug": "bear_stearns_2006", "deal_name": "Bear 2006", "vintage": 2006, "doc_count": 2, "status": "active"},
    ])
    cat.search_deals.return_value = cat.list_all_deals.return_value  # all match

    with patch("backend.vector.deal_catalog.DealCatalog", return_value=cat):
        runner = CliRunner()
        result = runner.invoke(cli, ["list-deals", "--scope", "bear*"])

    assert result.exit_code == 0, result.output


@patch("cli.main.load_config")
@patch("cli.main.RetrievalService")
def test_cli_search_backward_compatible(mock_rs_cls, mock_cfg):
    """search without any Phase 17 options still works (backward compat)."""
    mock_cfg.return_value = MagicMock()
    mock_rs_cls.return_value.execute.return_value = _mock_retrieval_result()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "what is a servicer"])

    assert result.exit_code == 0, result.output
    call_payload = mock_rs_cls.return_value.execute.call_args[0][0]
    # Defaults
    assert call_payload["doc_name_prefix"] is None
    assert call_payload["phase17_mode"] == "search"
    assert call_payload["phase17_scopes"] == []


def test_cli_mode_choice_validation():
    """--mode must be one of the allowed choices."""
    runner = CliRunner()
    result = runner.invoke(cli, ["search", "q", "--mode", "invalid_mode"])

    # Click rejects bad choices with exit code 2
    assert result.exit_code == 2
    assert "Invalid value" in result.output or "invalid" in result.output.lower()


@patch("cli.main.load_config")
@patch("cli.main.RetrievalService")
def test_cli_doc_filter_uppercased(mock_rs_cls, mock_cfg):
    """--doc-filter psa should be uppercased to PSA internally."""
    mock_cfg.return_value = MagicMock()
    mock_rs_cls.return_value.execute.return_value = _mock_retrieval_result()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "q", "--doc-filter", "psa"])

    assert result.exit_code == 0, result.output
    call_payload = mock_rs_cls.return_value.execute.call_args[0][0]
    assert call_payload["doc_name_prefix"] == "PSA"


@patch("cli.main.load_config")
@patch("cli.main.RetrievalService")
def test_cli_combine_all_options(mock_rs_cls, mock_cfg):
    """All 3 new options together: --doc-filter, --mode, --scopes."""
    mock_cfg.return_value = MagicMock()
    mock_rs_cls.return_value.execute.return_value = _mock_retrieval_result()

    runner = CliRunner()
    result = runner.invoke(cli, [
        "search", "distribution date",
        "--doc-filter", "PROSUPP",
        "--mode", "diff",
        "--scopes", "deal_a,deal_b",
    ])

    assert result.exit_code == 0, result.output
    call_payload = mock_rs_cls.return_value.execute.call_args[0][0]
    assert call_payload["doc_name_prefix"] == "PROSUPP"
    assert call_payload["phase17_mode"] == "diff"
    assert call_payload["phase17_scopes"] == ["deal_a", "deal_b"]


@patch("cli.main.load_config")
@patch("cli.main.RetrievalService")
def test_cli_compare_scopes_backward_compatible(mock_rs_cls, mock_cfg):
    """Legacy --compare-scopes still forwarded correctly."""
    mock_cfg.return_value = MagicMock()
    mock_rs_cls.return_value.execute.return_value = _mock_retrieval_result()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "q", "--compare-scopes", "a,b,c"])

    assert result.exit_code == 0, result.output
    call_payload = mock_rs_cls.return_value.execute.call_args[0][0]
    assert call_payload["compare_scopes"] == ["a", "b", "c"]


@patch("cli.main.load_config")
def test_cli_list_deals_json_format(mock_cfg):
    """list-deals --format json produces valid JSON."""
    mock_cfg.return_value = MagicMock()
    deals = [
        {"slug": "fin_deal1", "deal_name": "Deal One", "vintage": 2005, "doc_count": 3, "status": "active"},
    ]
    cat = MagicMock()
    cat.list_all_deals.return_value = deals

    with patch("backend.vector.deal_catalog.DealCatalog", return_value=cat):
        runner = CliRunner()
        result = runner.invoke(cli, ["list-deals", "--format", "json"])

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert parsed[0]["slug"] == "fin_deal1"
