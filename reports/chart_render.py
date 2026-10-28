"""
reports/chart_render.py - Static chart export for reports.

Renders the chart specs the Analyser shows in the browser (intelligence/charts.py), using
matplotlib at 150 DPI, so a chart in the PDF carries identical values, labels,
units and title to the one on screen. Nothing is screenshotted.

Returns base64 PNG, or None when a chart cannot be drawn. A failed chart never
raises into report generation.
"""

from __future__ import annotations

import base64
import io
from typing import Optional

import structlog

log = structlog.get_logger()

DPI = 150
# The same series colours as static/css/tokens.css (--series-1, --series-2).
SERIES_COLORS = ("#3987E5", "#D95926")


def _fig(width_in: float = 6.4, height_in: float = 2.8):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=DPI)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.6)
    ax.set_axisbelow(True)
    return fig, ax


def _finish(fig, ax, spec) -> str:
    if spec.get("title"):
        ax.set_title(spec["title"], fontsize=9, loc="left")
    if spec.get("x_label"):
        ax.set_xlabel(spec["x_label"], fontsize=8)
    if spec.get("y_label"):
        ax.set_ylabel(spec["y_label"], fontsize=8)
    ax.tick_params(labelsize=7)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=DPI)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _grouped_bar(spec) -> str:
    import numpy as np
    fig, ax = _fig()
    labels = spec["labels"]
    series = spec["series"]
    x = np.arange(len(labels))
    width = 0.8 / max(len(series), 1)
    for i, s in enumerate(series):
        # None stays a gap: matplotlib skips NaN rather than plotting a zero.
        vals = [np.nan if v is None else v for v in s["data"]]
        ax.bar(x + i * width - 0.4 + width / 2, vals, width,
               label=s["name"], color=SERIES_COLORS[i % len(SERIES_COLORS)])
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    if spec.get("y_format") == "percent":
        from matplotlib.ticker import PercentFormatter
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.legend(fontsize=7, frameon=False)
    return _finish(fig, ax, spec)


_RENDERERS = {"grouped_bar": _grouped_bar}


def render_chart_png_base64(spec: dict) -> Optional[str]:
    """Render one chart spec to a base64 PNG. Returns None if it cannot be drawn."""
    try:
        fn = _RENDERERS.get(spec.get("kind"))
        if not fn:
            return None
        return fn(spec)
    except Exception as e:
        log.info("static chart render failed", kind=spec.get("kind"), error=str(e)[:100])
        return None
