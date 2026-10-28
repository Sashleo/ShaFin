"""
reports/content.py - The content of an analysis report, built once and rendered
twice: to HTML for the PDF and to a Word document. Both show the same figures,
assumptions (with source and date), checks, ratios, models and flags.

A report model is {"title", "subtitle", "sections": [{"heading", "blocks"}]} where a
block is ("p", text), ("table", headers, rows) or ("chart", base64 PNG, caption).
"""

from __future__ import annotations

from intelligence.assumptions import ASSUMPTION_BY_KEY
from intelligence.display import fmt
from intelligence.fields import COMPANY_TYPES, fields_for
from intelligence.units import UNITS, format_rupees
from reports.chart_render import render_chart_png_base64

DISCLAIMER = (
    "Prepared with ShaFin from figures and assumptions entered by the user. ShaFin does not "
    "check figures against any source. This report is not investment advice."
)


def _fact_text(field, value) -> str:
    if value is None:
        return "—"
    if field.kind == "money":
        return format_rupees(value)
    if field.kind == "percent":
        return fmt(value, "pct")
    return f"{value:,}"


def _metric_rows(metrics) -> list:
    rows = []
    for m in metrics:
        note = ("Required: " + ", ".join(m.missing)) if m.missing else m.note
        rows.append([m.label, fmt(m.value, m.unit) if m.computed else "—", m.formula, note])
    return rows


def build_report_model(analysis: dict, company: dict, result, facts: dict, assumptions: dict,
                       charts: list, signing: dict) -> dict:
    ctype = company["company_type"]
    cur_l, pri_l = analysis["current_label"], analysis["prior_label"]
    sections = []

    # Figures
    rows = []
    for f in fields_for(ctype):
        cur, pri = facts["current"].get(f.key), facts["prior"].get(f.key)
        if cur is None and pri is None:
            continue
        rows.append([f.label, _fact_text(f, cur), _fact_text(f, pri)])
    sections.append({"heading": "Figures, as entered", "blocks": [
        ("p", f"Entered by the user in {UNITS[analysis['unit']][0]}; shown in whole rupees. "
              "Source of every figure: entered."),
        ("table", ["Figure", cur_l, pri_l], rows or [["No figures entered", "", ""]]),
    ]})

    # Assumptions
    a_rows = [[ASSUMPTION_BY_KEY[k].label, v["text"] + {"pct": "%", "x": "x", "years": " years",
               "pkr": " PKR"}[ASSUMPTION_BY_KEY[k].unit], v["source"], v["as_of"]]
              for k, v in assumptions.items()]
    sections.append({"heading": "Assumptions", "blocks": [
        ("p", "Entered for this analysis. ShaFin has no default rates."),
        ("table", ["Assumption", "Value", "Source", "Date"], a_rows or [["None entered", "", "", ""]]),
    ]})

    # Checks
    c_rows = []
    for c in result.checks:
        if c.passed is None:
            c_rows.append([c.label, "not run", "Required: " + ", ".join(c.missing)])
        else:
            c_rows.append([c.label, "adds up" if c.passed else "does not add up", f"{c.difference:,}"])
    sections.append({"heading": "Do the statements add up?",
                     "blocks": [("table", ["Check", "Result", "Difference (PKR)"], c_rows)]})

    # Ratios
    sections.append({"heading": "Bank ratios" if result.is_bank else "Ratios", "blocks": [
        ("table", ["Metric", cur_l, "Formula", "Note"], _metric_rows(result.metrics))]})

    # Models
    if result.is_bank:
        roe = result.metric("roe")
        sections.append({"heading": "Valuation: price to book against return on equity", "blocks": [
            ("table", ["Metric", "Value", "Formula", "Note"],
             _metric_rows(result.valuation)
             + [["Return on equity", fmt(roe.value, "pct") if roe.computed else "—", roe.formula, ""]]),
            ("p", "Altman Z: not applicable to banks. DCF: not applicable to banks."),
        ]})
    else:
        d = result.dupont
        dupont = (f"ROE {fmt(d.roe, 'pct')} = net margin {fmt(d.net_margin, 'pct')} x asset "
                  f"turnover {fmt(d.asset_turnover, 'x')} x equity multiplier "
                  f"{fmt(d.equity_multiplier, 'x')}" if d.roe is not None
                  else "Required: " + ", ".join(d.missing) if d.missing
                  else "Not defined: a denominator is zero.")
        sections.append({"heading": "DuPont", "blocks": [("p", dupont)]})

        z = result.altman
        z_blocks = [("p", z.model.citation)]
        if z.z is not None:
            z_blocks.insert(0, ("p", f"Z = {fmt(z.z, 'score')}: {z.zone} zone (safe above "
                                     f"{fmt(z.model.safe_above, 'two')}, distress below "
                                     f"{fmt(z.model.distress_below, 'two')})."))
            z_blocks.insert(1, ("table", ["Component", "Value"],
                                [[k, fmt(v, "ratio")] for k, v in z.components.items()]))
        else:
            z_blocks.insert(0, ("p", "Required: " + ", ".join(z.missing) if z.missing else z.note))
        sections.append({"heading": z.model.name, "blocks": z_blocks})

        v = result.dcf
        if v.missing:
            dcf_blocks = [("p", "The DCF did not run. Required: " + "; ".join(v.missing) + ".")]
        elif v.refused:
            dcf_blocks = [("p", v.refused)]
        else:
            dcf_blocks = [
                ("table", ["Input", "Value"], [
                    ["Cost of equity (risk-free + beta x ERP)", fmt(v.cost_of_equity, "pct")],
                    ["Cost of debt", fmt(v.cost_of_debt, "pct") + " (" + v.cost_of_debt_basis + ")"],
                    ["WACC", fmt(v.wacc, "pct")]]),
                ("table", ["Year", "Revenue", "FCFF", "Present value"],
                 [[str(y.year), fmt(y.revenue, "pkr"), fmt(y.fcff, "pkr"), fmt(y.pv, "pkr")]
                  for y in v.years]),
                ("table", ["Result", "Value"], [
                    ["Terminal value", fmt(v.terminal_value, "pkr")],
                    ["Enterprise value", fmt(v.enterprise_value, "pkr")],
                    ["Net debt", fmt(v.net_debt, "pkr")],
                    ["Equity value", fmt(v.equity_value, "pkr")],
                    ["Value per share", fmt(v.per_share, "per_share")]]),
                ("table", ["WACC \\ growth"] + [fmt(g, "pct") for g in v.sensitivity_growths],
                 [[fmt(w, "pct")] + ["n/a" if v.sensitivity[(w, g)] is None
                                     else fmt(v.sensitivity[(w, g)], "per_share")
                                     for g in v.sensitivity_growths]
                  for w in v.sensitivity_waccs]),
            ]
        sections.append({"heading": "Discounted cash flow (FCFF)", "blocks": dcf_blocks})

    # Profit bridge
    b = result.bridge
    if b.components:
        b_rows = ([[f"Profit after tax, {pri_l}", format_rupees(b.start)]]
                  + [[label, f"{value:+,}"] for label, value in b.components]
                  + [[f"Profit after tax, {cur_l}", format_rupees(b.end)]])
        bridge_blocks = [("table", ["Item", "PKR"], b_rows)]
    else:
        bridge_blocks = [("p", "Required: " + ", ".join(b.missing))]
    sections.append({"heading": f"Profit bridge: {pri_l} to {cur_l}", "blocks": bridge_blocks})

    # Flags
    h = result.health
    if h.score is not None:
        f_rows = [[f.label, fmt(f.value, f.unit), f"{f.op} {f.threshold}", "met" if f.passed else "flag",
                   f.rationale] for f in h.flags]
        flag_blocks = [("p", f"{h.passed} of {h.evaluated} thresholds met: {fmt(h.score, 'one')} / 10."),
                       ("table", ["Metric", "Value", "Threshold", "Result", "Rationale"], f_rows)]
    else:
        flag_blocks = [("p", "No threshold could be evaluated.")]
    sections.append({"heading": "Flags", "blocks": flag_blocks})

    # Charts
    chart_blocks = []
    for spec in charts:
        png = render_chart_png_base64(spec)
        if png:
            chart_blocks.append(("chart", png, spec["title"]))
    if chart_blocks:
        sections.append({"heading": "Charts", "blocks": chart_blocks})

    sections.append({"heading": "About this report", "blocks": [
        ("p", DISCLAIMER),
        ("p", f"Signed with {signing['algorithm']} (post-quantum, NIST FIPS 204), key fingerprint "
              f"{signing['fingerprint']}. The signature is kept beside the file and checked before "
              "every download. Stored encrypted with AES-256-GCM."),
    ]})
    return {
        "title": f"{company['name']}: {analysis['name']}",
        "subtitle": f"{COMPANY_TYPES[ctype]} · {cur_l} against {pri_l}",
        "sections": sections,
    }
