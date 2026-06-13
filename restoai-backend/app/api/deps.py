"""FastAPI dependency factories.

This is the ONLY file in app/api/ that is permitted to import from
app.db. All routers import get_session from here rather than from
app.db.engine directly — keeping the api→db import in one place and
letting test_layering.py enforce the boundary on everything else.
"""
from app.db.engine import get_session as _get_session

# Re-export so routers can: from app.api.deps import get_session
get_session = _get_session
