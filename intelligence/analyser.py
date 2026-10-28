"""
intelligence/analyser.py - One entry point: entered figures and assumptions in,
every applicable calculation out, chosen by company type.

  manufacturer      ratios, DuPont, Altman Z,   DCF, profit bridge, checks, flags
  non_manufacturer  ratios, DuPont, Altman Z'', DCF, profit bridge, checks, flags
  bank              bank ratios, P/B beside ROE, P/E, profit bridge, checks, flags
                    (no Altman, no DCF)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from intelligence.altman import AltmanResult, compute_altman
from intelligence.bank import compute_bank_ratios, compute_bank_valuation
from intelligence.bridge import Bridge, compute_bridge
from intelligence.checks import run_checks
from intelligence.dcf import DCFResult, compute_dcf
from intelligence.flags import Health, evaluate
from intelligence.ratios import DuPont, compute_dupont, compute_ratios


@dataclass
class Analysis:
    company_type: str
    checks: list
    metrics: list
    bridge: Bridge
    health: Health
    altman: AltmanResult
    dupont: Optional[DuPont] = None
    dcf: Optional[DCFResult] = None
    valuation: list = field(default_factory=list)

    @property
    def is_bank(self) -> bool:
        return self.company_type == "bank"

    def metric(self, key: str):
        return next((m for m in self.metrics + self.valuation if m.key == key), None)


def analyse(company_type: str, facts: dict, assumptions: dict, thresholds: list[dict],
            tolerance: int) -> Analysis:
    """facts: {"current": {...}, "prior": {...}}; assumptions: {key: Fraction}."""
    cur, prior = facts.get("current", {}), facts.get("prior", {})
    price = assumptions.get("share_price")
    if company_type == "bank":
        metrics = compute_bank_ratios(cur, prior)
        valuation = compute_bank_valuation(cur, price)
        return Analysis(
            company_type=company_type,
            checks=run_checks(company_type, cur, prior, tolerance),
            metrics=metrics,
            bridge=compute_bridge(company_type, cur, prior),
            health=evaluate(metrics, thresholds),
            altman=compute_altman(company_type, cur),
            valuation=valuation,
        )
    metrics = compute_ratios(cur, prior)
    return Analysis(
        company_type=company_type,
        checks=run_checks(company_type, cur, prior, tolerance),
        metrics=metrics,
        bridge=compute_bridge(company_type, cur, prior),
        health=evaluate(metrics, thresholds),
        altman=compute_altman(company_type, cur, price),
        dupont=compute_dupont(cur),
        dcf=compute_dcf(cur, prior, assumptions),
    )
