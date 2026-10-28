"""
routers/common.py - The one Jinja2 environment every router renders with.

Autoescaping is on for every template. Filters: fmt (metric values), rupees
(whole rupees), unit_text (rupees shown in the analysis's unit).
"""

from fastapi import Request
from fastapi.templating import Jinja2Templates

from config.settings import settings
from intelligence.display import fmt
from intelligence.fields import COMPANY_TYPES
from intelligence.units import UNITS, format_rupees, from_rupees

templates = Jinja2Templates(directory="templates")
templates.env.filters["fmt"] = fmt
templates.env.filters["rupees"] = format_rupees
templates.env.filters["unit_text"] = from_rupees
templates.env.globals["COMPANY_TYPES"] = COMPANY_TYPES
templates.env.globals["UNITS"] = UNITS
templates.env.globals["DEMO_MODE"] = settings.DEMO_MODE
if settings.DEMO_MODE:
    from demo.loader import DEMO_PASSWORD
    templates.env.globals["demo_password"] = DEMO_PASSWORD


def user_of(request: Request) -> str:
    """The signed-in user's id, as the session records it."""
    return getattr(request.state, "user_id", None) or "unknown"
