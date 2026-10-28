"""
reports/pdf_renderer.py — PDF rendering of a report model with WeasyPrint.

The HTML comes from templates/report/report.html with autoescaping on. WeasyPrint
fetches nothing: the template has no external resources, charts are embedded as
data URIs, and any other URL is refused.
"""

import weasyprint
from jinja2 import Environment, FileSystemLoader, select_autoescape

_env = Environment(loader=FileSystemLoader("templates"),
                   autoescape=select_autoescape(["html"]))


def render_html(model: dict, generated_at: str) -> str:
    return _env.get_template("report/report.html").render(model=model, generated_at=generated_at)


def _data_uris_only(url: str, *args, **kwargs):
    if url.startswith("data:"):
        return weasyprint.default_url_fetcher(url, *args, **kwargs)
    raise ValueError(f"ShaFin reports load no external resources: {url[:60]}")


def render_pdf(model: dict, generated_at: str) -> bytes:
    return weasyprint.HTML(string=render_html(model, generated_at),
                           url_fetcher=_data_uris_only).write_pdf()
