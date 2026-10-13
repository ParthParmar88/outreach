"""
Every model must be imported here.

Alembic discovers tables through Base.metadata, and a model that is never
imported is invisible to it. A missing import here is the usual reason a
migration comes out empty.
"""

from outreach.db.base import Base
from outreach.db.models.lead import STATES, Lead
from outreach.db.models.password_reset import PasswordReset
from outreach.db.models.product import CrawlMode, CrawlState, Product, ProductPage
from outreach.db.models.search_run import SearchRun
from outreach.db.models.tracked_post import Outcome, TrackedPost, TrackState
from outreach.db.models.user import User

__all__ = [
    "STATES",
    "Base",
    "CrawlMode",
    "CrawlState",
    "Lead",
    "Outcome",
    "PasswordReset",
    "Product",
    "ProductPage",
    "SearchRun",
    "TrackState",
    "TrackedPost",
    "User",
]
