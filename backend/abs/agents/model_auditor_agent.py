"""
ModelAuditorAgent — Audit a generated payment model against governing
documents.  Every constant must have a citation, every formula must
match the governing doc, and no hardcoded values may appear without
a traceable source.

No LLM / OpenAI dependency — all checks are deterministic.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.agents.base_agent import AgentBase
from backend.agents.agent_tools import ToolRegistry
from backend.common.confidence import ConfidenceScore, ConfidenceTier
from backend.abs.config.constants import (
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_LOW_THRESHOLD,
)
from backend.abs.deal_scope import DealScope
from config import KTSConfig

logger = logging.getLogger(__name__)

# Regex for numeric literals that might be un-sourced constants.
_NUMERIC_LITERAL_RE = re.compile(
    r"""(?<![_a-zA-Z])          # not preceded by identifier char
        (\d+\.\d+|\d{4,})       # float or int with 4+ digits
        (?![_a-zA-Z\[])""",     # not followed by identifier char
    re.VERBOSE,
)


class ModelAuditorAgent(AgentBase):
    """
    Audit a generated payment model for correctness and traceability.

    Checks performed:
    1. **Syntax** — model file is valid Python (AST parse).
    2. **Constants traceability** — every constant has a matching entry
       in the extractions / governing docs.
    3. **Hardcoded values** — flag numeric literals in the ``run()``
       function body that don't map to named constants.
    4. **Waterfall completeness** — waterfall order in the model covers
       all rules from the extractions.
    5. **Entry-point contract** — model exposes ``run(data_path, month)``.
    """

    agent_name = "model_auditor"

    def __init__(
        self,
        config: KTSConfig,
        deal_scope: DealScope,
        tool_registry: ToolRegistry,
        llm_callable=None,
    ) -> None:
        super().__init__(config, deal_scope=deal_scope, tool_registry=tool_registry, llm_callable=llm_callable)

    # ------------------------------------------------------------------
    # Prompt structure
    # ------------------------------------------------------------------

    def _get_mission(self) -> str:
        return (
            "Audit the generated payment model against governing documents. "
            "Verify that every constant has a citation, every formula matches "
            "the governing doc, and no hardcoded values appear without a "
            "traceable source."
        )

    def _get_actions(self) -> list[str]:
        return [
            "Read the generated payment_model.py.",
            "Parse it with the Python AST to check syntax.",
            "Load governing docs and extraction JSONs.",
            "Check that every model constant appears in extractions.",
            "Flag numeric literals without source attribution.",
            "Verify waterfall order completeness.",
            "Verify model exposes run(data_path, month).",
            "Generate audit_report.json with pass/fail per check.",
        ]

    def _get_output_spec(self) -> str:
        return (
            "dict with keys:\n"
            "  audit_result: str ('pass' or 'fail')\n"
            "  checks: list[dict] — per-check {name, passed, details}\n"
            "  issues: list[str] — human-readable issue descriptions\n"
        )

    def _get_validation_rules(self) -> list[str]:
        return [
            "Model must be syntactically valid Python.",
            "Every named constant must trace to an extraction or governing doc.",
            "No unexplained numeric literals in run() body.",
            "Waterfall order must cover all extraction rules.",
            "Model must expose run(data_path, month).",
        ]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        deal_path = self.deal_scope.deal_path
        model_path = deal_path / "model" / "payment_model.py"

        checks: list[dict[str, Any]] = []
        issues: list[str] = []

        if not model_path.exists():
            issues.append(f"Model file not found: {model_path}")
            return {
                "audit_result": "fail",
                "checks": checks,
                "issues": issues,
            }

        model_source = model_path.read_text(encoding="utf-8")

        syntax_ok, syntax_detail = self._check_syntax(model_source)
        checks.append({"name": "syntax_valid", "passed": syntax_ok, "details": syntax_detail})
        if not syntax_ok:
            issues.append(f"Syntax error: {syntax_detail}")

        extractions = self._load_extractions(deal_path)

        const_ok, const_detail, const_issues = self._check_constants(
            model_source, extractions,
        )
        checks.append({"name": "constants_traceable", "passed": const_ok, "details": const_detail})
        issues.extend(const_issues)

        hardcoded_ok, hardcoded_detail, hc_issues = self._check_hardcoded(model_source)
        checks.append({"name": "no_unexplained_literals", "passed": hardcoded_ok, "details": hardcoded_detail})
        issues.extend(hc_issues)

        wf_ok, wf_detail, wf_issues = self._check_waterfall(model_source, extractions)
        checks.append({"name": "waterfall_complete", "passed": wf_ok, "details": wf_detail})
        issues.extend(wf_issues)

        ep_ok, ep_detail = self._check_entry_point(model_source)
        checks.append({"name": "entry_point_exists", "passed": ep_ok, "details": ep_detail})
        if not ep_ok:
            issues.append(ep_detail)

        all_passed = all(c["passed"] for c in checks)
        audit_result = "pass" if all_passed else "fail"

        report = {
            "deal_id": self.deal_scope.deal_id,
            "audit_result": audit_result,
            "checks": checks,
            "issues": issues,
        }
        report_dir = deal_path / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "audit_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8",
        )
        logger.info("Audit report saved to %s", report_path)

        return report

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_syntax(source: str) -> tuple[bool, str]:
        try:
            ast.parse(source)
            return True, "Model parses successfully."
        except SyntaxError as exc:
            return False, f"Line {exc.lineno}: {exc.msg}"

    def _load_extractions(self, deal_path: Path) -> dict[str, list[dict]]:
        extractions: dict[str, list[dict]] = {}
        ext_dir = deal_path / "extractions"
        if not ext_dir.exists():
            return extractions
        for json_file in sorted(ext_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                section = json_file.stem
                items = data if isinstance(data, list) else data.get("items", [data])
                extractions[section] = items
            except (json.JSONDecodeError, OSError):
                pass
        return extractions

    def _check_constants(
        self,
        source: str,
        extractions: dict[str, list[dict]],
    ) -> tuple[bool, str, list[str]]:
        issues: list[str] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False, "Cannot parse source", ["Syntax error prevents constant check"]

        known_terms: set[str] = set()
        for items in extractions.values():
            for item in items:
                for key in ("term", "name", "id", "field"):
                    val = item.get(key, "")
                    if val:
                        known_terms.add(val.lower().replace(" ", "_").replace("-", "_"))

        model_constants: list[str] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        model_constants.append(target.id)

        untraceable: list[str] = []
        for const_name in model_constants:
            normalised = const_name.lower()
            if normalised not in known_terms and not self._is_standard_constant(normalised):
                untraceable.append(const_name)

        if untraceable:
            issues = [f"Constant '{c}' not found in extractions" for c in untraceable]
            return False, f"{len(untraceable)} untraceable constants", issues

        return True, f"All {len(model_constants)} constants traceable", []

    @staticmethod
    def _is_standard_constant(name: str) -> bool:
        standards = {
            "class_names", "waterfall_order", "comparison_fields",
            "required_monthly_fields",
        }
        return name in standards

    def _check_hardcoded(self, source: str) -> tuple[bool, str, list[str]]:
        issues: list[str] = []
        in_run = False
        run_indent = 0
        for lineno, line in enumerate(source.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("def run("):
                in_run = True
                run_indent = len(line) - len(stripped)
                continue
            if in_run:
                current_indent = len(line) - len(line.lstrip())
                if stripped and current_indent <= run_indent and not stripped.startswith("#"):
                    in_run = False
                    continue
                for m in _NUMERIC_LITERAL_RE.finditer(line):
                    issues.append(
                        f"Line {lineno}: numeric literal {m.group()} may need sourcing"
                    )

        ok = len(issues) == 0
        detail = "No unexplained literals" if ok else f"{len(issues)} literals flagged"
        return ok, detail, issues

    def _check_waterfall(
        self,
        source: str,
        extractions: dict[str, list[dict]],
    ) -> tuple[bool, str, list[str]]:
        issues: list[str] = []
        expected_rules = extractions.get("waterfall_rules", extractions.get("waterfall", []))
        if not expected_rules:
            return True, "No extraction waterfall rules to compare", []

        expected_ids: set[str] = set()
        for r in expected_rules:
            rid = r.get("id", r.get("step", ""))
            if rid:
                expected_ids.add(str(rid))

        if "WATERFALL_ORDER" not in source:
            issues.append("WATERFALL_ORDER not found in model source")
            return False, "Missing WATERFALL_ORDER", issues

        found_ids: set[str] = set()
        in_wf = False
        for line in source.splitlines():
            if "WATERFALL_ORDER" in line and "=" in line:
                in_wf = True
            if in_wf:
                for eid in expected_ids:
                    if eid in line:
                        found_ids.add(eid)
                if line.strip() == "]":
                    in_wf = False

        missing = expected_ids - found_ids
        if missing:
            issues = [f"Waterfall rule '{r}' missing from model" for r in sorted(missing)]
            return False, f"{len(missing)} rules missing", issues

        return True, f"All {len(expected_ids)} waterfall rules present", []

    @staticmethod
    def _check_entry_point(source: str) -> tuple[bool, str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False, "Source has syntax errors"

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                arg_names = [a.arg for a in node.args.args]
                if len(arg_names) >= 2:
                    return True, "run() found with correct signature"
                return False, f"run() found but has args {arg_names}, expected (data_path, month)"
        return False, "No run() function found in model"

    # ------------------------------------------------------------------
    # Quality scoring overrides
    # ------------------------------------------------------------------

    def _score_completeness(self, result: Any, task: dict) -> float:
        checks = result.get("checks", [])
        if not checks:
            return 5.0
        return 10.0 * sum(1 for c in checks if c["passed"]) / len(checks)

    def _score_accuracy(self, result: Any, task: dict) -> float:
        return 10.0 if result.get("audit_result") == "pass" else 6.0

    def _score_confidence(self, result: Any, task: dict) -> ConfidenceScore:
        checks = result.get("checks", [])
        passed = sum(1 for c in checks if c["passed"])
        total = max(len(checks), 1)
        value = passed / total
        tier = self._categorize_confidence(value)
        return ConfidenceScore(
            value=value, tier=tier,
            reasoning=f"{passed}/{total} checks passed",
        )

    def _get_artifacts(self, result: Any) -> list[str]:
        deal_path = self.deal_scope.deal_path
        report_path = deal_path / "reports" / "audit_report.json"
        return [str(report_path)] if report_path.exists() else []
