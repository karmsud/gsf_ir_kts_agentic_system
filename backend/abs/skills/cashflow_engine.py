"""
Cashflow Engine — Run monthly cashflow projections with scenario injection.
Implements the core waterfall payment distribution logic.

Ported from PayGen pipeline.skills.cashflow_engine → backend.abs.skills
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class MonthlyResult:
    """Result of a single month's cashflow distribution."""
    month: int
    collections: dict[str, float] = field(default_factory=dict)
    distributions: list[dict[str, Any]] = field(default_factory=list)
    class_balances: dict[str, dict[str, float]] = field(default_factory=dict)
    trigger_states: dict[str, bool] = field(default_factory=dict)
    available_funds: float = 0.0
    remaining_funds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "month": self.month,
            "collections": self.collections,
            "distributions": self.distributions,
            "class_balances": self.class_balances,
            "trigger_states": self.trigger_states,
            "available_funds": round(self.available_funds, 2),
            "remaining_funds": round(self.remaining_funds, 2),
            "errors": self.errors,
        }


@dataclass
class ProjectionResult:
    """Full projection across all months."""
    deal_id: str
    scenario: str
    months: list[MonthlyResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "scenario": self.scenario,
            "total_months": len(self.months),
            "months": [m.to_dict() for m in self.months],
            "summary": self.summary,
        }


def run_projections(
    waterfall_rules: list[dict],
    classes_setup: list[dict],
    monthly_inputs: list[dict],
    deal_id: str = "",
    scenario: str = "base",
    scenario_overrides: Optional[dict[str, Any]] = None,
    loss_allocations: Optional[list[dict]] = None,
    triggers: Optional[list[dict]] = None,
    accounts: Optional[list[dict]] = None,
) -> ProjectionResult:
    """
    Run cashflow projections across all months.

    Args:
        waterfall_rules: Ordered list of waterfall payment rules
        classes_setup: Initial class setup data
        monthly_inputs: Per-month input data (collections, defaults, etc.)
        deal_id: Deal identifier
        scenario: Scenario name (base, stress, etc.)
        scenario_overrides: Override parameters for scenario analysis
        loss_allocations: Loss allocation rules
        triggers: Trigger definitions
        accounts: Account definitions

    Returns:
        ProjectionResult with per-month and summary data
    """
    result = ProjectionResult(deal_id=deal_id, scenario=scenario)

    # Initialize class balances from classes_setup
    class_balances = _init_class_balances(classes_setup)

    # Initialize trigger states
    trigger_states: dict[str, bool] = {}
    if triggers:
        for trig in triggers:
            name = trig.get("name", trig.get("id", ""))
            trigger_states[name] = False

    # Initialize accounts
    account_balances: dict[str, float] = {}
    if accounts:
        for acct in accounts:
            name = acct.get("name", acct.get("id", ""))
            initial = _parse_amount(acct.get("initial_balance", 0))
            account_balances[name] = initial

    # Process each month
    for month_idx, month_input in enumerate(monthly_inputs, start=1):
        # Apply scenario overrides
        adjusted_input = copy.deepcopy(month_input)
        if scenario_overrides:
            adjusted_input = _apply_scenario_overrides(adjusted_input, scenario_overrides)

        month_result = _process_month(
            month=month_idx,
            month_input=adjusted_input,
            waterfall_rules=waterfall_rules,
            class_balances=class_balances,
            trigger_states=trigger_states,
            account_balances=account_balances,
            loss_allocations=loss_allocations or [],
            trigger_definitions=triggers or [],
        )

        # Update balances for next month
        class_balances = copy.deepcopy(month_result.class_balances)
        trigger_states = copy.deepcopy(month_result.trigger_states)

        result.months.append(month_result)

    # Generate summary
    result.summary = _generate_summary(result)

    return result


def save_projections(result: ProjectionResult, output_path: Path) -> Path:
    """Save projection results to JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    return output_path


# ── Internal Processing ───────────────────────────────────────

def _process_month(
    month: int,
    month_input: dict,
    waterfall_rules: list[dict],
    class_balances: dict[str, dict[str, float]],
    trigger_states: dict[str, bool],
    account_balances: dict[str, float],
    loss_allocations: list[dict],
    trigger_definitions: Optional[list[dict]] = None,
) -> MonthlyResult:
    """Process a single month through the waterfall."""
    result = MonthlyResult(month=month)

    # Collect monthly cash
    collections = _collect_cash(month_input)
    result.collections = collections
    available_funds = sum(collections.values())
    result.available_funds = available_funds

    # Evaluate triggers
    result.trigger_states = _evaluate_triggers(
        trigger_states, class_balances, month_input, month,
        trigger_definitions=trigger_definitions,
    )

    # Apply loss allocations
    losses = _parse_amount(month_input.get("realized_losses", 0))
    if losses > 0 and loss_allocations:
        class_balances = _apply_losses(class_balances, losses, loss_allocations)

    # Run waterfall rules in order
    remaining = available_funds
    for rule in waterfall_rules:
        step = rule.get("step", rule.get("id", f"rule_{waterfall_rules.index(rule)}"))
        target = rule.get("target", rule.get("account", rule.get("class", "")))

        # Check trigger conditions
        condition = rule.get("condition", "")
        if condition and not _check_condition(condition, result.trigger_states):
            result.distributions.append({
                "step": step,
                "target": target,
                "amount": 0.0,
                "skipped": True,
                "reason": f"Condition not met: {condition}",
            })
            continue

        # Calculate distribution amount
        dist_amount = _calculate_distribution(
            rule, remaining, class_balances, month_input
        )
        dist_amount = min(dist_amount, remaining)  # Can't exceed remaining

        remaining -= dist_amount

        result.distributions.append({
            "step": step,
            "target": target,
            "amount": round(dist_amount, 2),
            "remaining_after": round(remaining, 2),
        })

        # Update target balance
        if target in class_balances:
            class_balances[target]["principal_paid"] = (
                class_balances[target].get("principal_paid", 0) + dist_amount
            )
        if target in account_balances:
            account_balances[target] += dist_amount

    result.class_balances = class_balances
    result.remaining_funds = remaining

    return result


def _init_class_balances(classes_setup: list[dict]) -> dict[str, dict[str, float]]:
    """Initialize class balances from setup data."""
    balances: dict[str, dict[str, float]] = {}
    for cls in classes_setup:
        name = cls.get("class_name", cls.get("name", cls.get("id", "")))
        if not name:
            continue
        balances[name] = {
            "original_balance": _parse_amount(cls.get("original_balance", 0)),
            "current_balance": _parse_amount(cls.get("current_balance",
                                              cls.get("original_balance", 0))),
            "coupon_rate": _parse_rate(cls.get("coupon_rate", cls.get("interest_rate", 0))),
            "principal_paid": 0.0,
            "interest_paid": 0.0,
            "losses_allocated": 0.0,
        }
    return balances


def _collect_cash(month_input: dict) -> dict[str, float]:
    """Extract cash collections from monthly input."""
    collections: dict[str, float] = {}
    for key in ["principal_collections", "interest_collections",
                "prepayments", "recoveries", "other_income"]:
        val = month_input.get(key)
        if val is not None:
            collections[key] = _parse_amount(val)
    return collections


def _evaluate_triggers(
    current_states: dict[str, bool],
    class_balances: dict[str, dict[str, float]],
    month_input: dict,
    month: int,
    trigger_definitions: Optional[list[dict]] = None,
) -> dict[str, bool]:
    """
    Evaluate trigger conditions based on current deal state.

    Supports the following trigger condition types:
      - Delinquency rate thresholds
      - Cumulative loss thresholds
      - Overcollateralization (OC) tests
      - Subordination ratio tests
      - Custom threshold-based triggers
    """
    updated_states = copy.deepcopy(current_states)

    if not trigger_definitions:
        return updated_states

    # Compute metrics available for trigger evaluation
    total_current_balance = sum(
        b.get("current_balance", 0) for b in class_balances.values()
    )
    total_original_balance = sum(
        b.get("original_balance", 0) for b in class_balances.values()
    )
    total_losses = sum(
        b.get("losses_allocated", 0) for b in class_balances.values()
    )

    # Pool-level metrics from month input
    pool_balance = _parse_amount(
        month_input.get("pool_balance", month_input.get("current_pool_balance", 0))
    )
    delinquency_60 = _parse_amount(
        month_input.get("delinquency_60_plus",
                        month_input.get("delinquency_rate", 0))
    )
    cumulative_losses = _parse_amount(
        month_input.get("cumulative_losses",
                        month_input.get("cumulative_realized_losses", total_losses))
    )
    original_pool = _parse_amount(
        month_input.get("original_pool_balance", total_original_balance)
    )

    # Compute ratios
    loss_rate = cumulative_losses / original_pool if original_pool > 0 else 0
    delinquency_rate = delinquency_60

    for trigger in trigger_definitions:
        name = trigger.get("name", trigger.get("id", ""))
        if not name:
            continue

        condition = trigger.get("condition", trigger.get("description", "")).lower()
        threshold = _parse_amount(trigger.get("threshold", 0))
        trigger_type = trigger.get("type", "").lower()

        tripped = False

        # ── Type-based evaluation ──
        if trigger_type == "delinquency" or "delinquen" in condition:
            if threshold > 0:
                tripped = delinquency_rate > threshold
            elif "%" in trigger.get("condition", ""):
                pct = _extract_percentage(trigger.get("condition", ""))
                if pct is not None:
                    tripped = delinquency_rate > pct

        elif trigger_type == "cumulative_loss" or "cumulative" in condition:
            if threshold > 0:
                tripped = loss_rate > threshold
            elif "%" in trigger.get("condition", ""):
                pct = _extract_percentage(trigger.get("condition", ""))
                if pct is not None:
                    tripped = loss_rate > pct

        elif trigger_type == "overcollateralization" or "overcollateral" in condition:
            if pool_balance > 0 and total_current_balance > 0:
                oc_ratio = pool_balance / total_current_balance
                if threshold > 0:
                    tripped = oc_ratio < threshold
                else:
                    tripped = oc_ratio < 1.0

        elif trigger_type == "subordination" or "subordinat" in condition:
            senior_balance = sum(
                b.get("current_balance", 0)
                for n, b in class_balances.items()
                if "a" in n.lower()
            )
            sub_balance = total_current_balance - senior_balance
            if total_current_balance > 0:
                sub_ratio = sub_balance / total_current_balance
                if threshold > 0:
                    tripped = sub_ratio < threshold

        elif trigger_type == "balance" or "balance" in condition:
            if threshold > 0:
                tripped = total_current_balance < threshold

        elif threshold > 0:
            tripped = loss_rate > threshold

        # Triggers are sticky: once tripped, they stay tripped
        # unless explicitly designed to cure
        cure_allowed = trigger.get("cure_allowed", False)
        if cure_allowed:
            updated_states[name] = tripped
        else:
            updated_states[name] = current_states.get(name, False) or tripped

    return updated_states


def _extract_percentage(text: str) -> Optional[float]:
    """Extract a percentage value from text and return as decimal."""
    import re
    m = re.search(r'([\d.]+)\s*%', text)
    if m:
        return float(m.group(1)) / 100.0
    return None


def _apply_losses(
    class_balances: dict[str, dict[str, float]],
    total_losses: float,
    loss_allocations: list[dict],
) -> dict[str, dict[str, float]]:
    """Apply realized losses to classes per allocation rules."""
    remaining_loss = total_losses

    sorted_allocs = sorted(
        loss_allocations,
        key=lambda x: x.get("priority", 999),
    )

    for alloc in sorted_allocs:
        if remaining_loss <= 0:
            break
        target = alloc.get("class", alloc.get("target", ""))
        if target not in class_balances:
            continue

        balance = class_balances[target].get("current_balance", 0)
        loss_amount = min(remaining_loss, balance)

        class_balances[target]["current_balance"] -= loss_amount
        class_balances[target]["losses_allocated"] += loss_amount
        remaining_loss -= loss_amount

    return class_balances


def _calculate_distribution(
    rule: dict,
    available: float,
    class_balances: dict[str, dict[str, float]],
    month_input: dict,
) -> float:
    """Calculate distribution amount for a waterfall rule."""
    amount_type = rule.get("amount_type", "").lower()

    if amount_type == "fixed":
        return _parse_amount(rule.get("amount", 0))

    if amount_type == "interest":
        target = rule.get("target", rule.get("class", ""))
        if target in class_balances:
            balance = class_balances[target].get("current_balance", 0)
            rate = class_balances[target].get("coupon_rate", 0)
            return balance * rate / 12  # monthly interest

    if amount_type == "principal":
        return available  # Sequential: give all remaining to this class

    if amount_type == "percentage":
        pct = _parse_rate(rule.get("percentage", 0))
        return available * pct

    # Default: available funds
    return available


def _check_condition(condition: str, trigger_states: dict[str, bool]) -> bool:
    """Check if a trigger condition is met."""
    condition_lower = condition.lower().strip()

    for name, state in trigger_states.items():
        if name.lower() in condition_lower:
            if "not" in condition_lower or "no" in condition_lower:
                return not state
            return state

    return True  # Default: condition met


def _apply_scenario_overrides(
    month_input: dict,
    overrides: dict[str, Any],
) -> dict:
    """Apply scenario parameter overrides to month input."""
    adjusted = copy.deepcopy(month_input)

    for key, value in overrides.items():
        if key.endswith("_multiplier"):
            base_key = key.replace("_multiplier", "")
            if base_key in adjusted:
                adjusted[base_key] = _parse_amount(adjusted[base_key]) * float(value)
        elif key.endswith("_override"):
            base_key = key.replace("_override", "")
            adjusted[base_key] = value
        else:
            adjusted[key] = value

    return adjusted


def _generate_summary(result: ProjectionResult) -> dict[str, Any]:
    """Generate summary statistics across all months."""
    if not result.months:
        return {}

    total_distributions = 0.0
    total_collections = 0.0

    for month in result.months:
        total_collections += sum(month.collections.values())
        total_distributions += sum(
            d["amount"] for d in month.distributions if not d.get("skipped")
        )

    final_balances = result.months[-1].class_balances if result.months else {}

    return {
        "total_months": len(result.months),
        "total_collections": round(total_collections, 2),
        "total_distributions": round(total_distributions, 2),
        "final_class_balances": {
            k: round(v.get("current_balance", 0), 2)
            for k, v in final_balances.items()
        },
    }


def _parse_amount(val: Any) -> float:
    """Parse a monetary amount."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        import re
        cleaned = re.sub(r'[$,\s]', '', val.strip())
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def _parse_rate(val: Any) -> float:
    """Parse a rate/percentage value."""
    if isinstance(val, (int, float)):
        v = float(val)
        return v / 100.0 if v > 1.0 else v
    if isinstance(val, str):
        import re
        cleaned = re.sub(r'[%\s]', '', val.strip())
        try:
            v = float(cleaned)
            return v / 100.0 if v > 1.0 else v
        except ValueError:
            return 0.0
    return 0.0
