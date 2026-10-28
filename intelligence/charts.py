"""
intelligence/charts.py - Chart specs for the Analyser page and the reports.

The same spec is drawn by static/js/charts.js in the browser and by
reports/chart_render.py in the PDF, so both show identical values. Values are
rounded here for drawing only.
"""

from __future__ import annotations

from typing import Optional

from intelligence.ratios import compute_ratios

_MARGINS = (("gross_margin", "Gross"), ("operating_margin", "Operating"), ("net_margin", "Net"))


def bridge_chart(bridge) -> Optional[dict]:
    """Bars for each profit-bridge component (rupees), when the bridge is computed."""
    if not bridge.components:
        return None
    return {
        "kind": "grouped_bar",
        "title": "What changed profit after tax (PKR)",
        "labels": [label for label, _ in bridge.components],
        "series": [{"name": "Change from prior year",
                    "data": [int(v) for _, v in bridge.components]}],
    }


def margins_chart(result, prior_facts: dict, analysis: dict) -> Optional[dict]:
    """Gross, operating and net margin, current against prior. Non-banks only."""
    if result.is_bank:
        return None
    current = {m.key: m.value for m in result.metrics}
    prior = {m.key: m.value for m in compute_ratios(prior_facts, {})}
    if all(current.get(k) is None for k, _ in _MARGINS):
        return None

    def series(values):
        return [None if values.get(k) is None else round(float(values[k]), 4) for k, _ in _MARGINS]

    return {
        "kind": "grouped_bar",
        "title": "Margins",
        "y_format": "percent",
        "labels": [label for _, label in _MARGINS],
        "series": [{"name": analysis["prior_label"], "data": series(prior)},
                   {"name": analysis["current_label"], "data": series(current)}],
    }
