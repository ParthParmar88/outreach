"""Settings via pydantic-settings. All env vars declared here, nowhere else."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- app -------------------------------------------------------------
    app_env: str = "local"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    # ---- accounts --------------------------------------------------------
    #: Signs session cookies. Changing it logs everybody out, which is the
    #: intended emergency lever. MUST be set to something random in
    #: production: the default below is public knowledge.
    secret_key: str = "dev-only-not-a-secret-change-me"
    session_days: int = Field(default=30, ge=1)
    #: Send the cookie over https only. False locally because dev is http.
    cookie_secure: bool = False

    # ---- email -----------------------------------------------------------
    #: Where the app lives, for links inside emails. The reset link has to
    #: point at the screen a person clicks, not at this API.
    app_url: str = "http://localhost:5173"

    #: Empty means no mail can be sent. The reset link is then written to the
    #: server log instead, and the API says plainly that nothing was sent -
    #: a reset flow that silently delivers nothing is worse than one that
    #: admits it.
    smtp_host: str = ""

    # ---- database --------------------------------------------------------
    database_url: str = "postgresql+asyncpg://outreach:outreach@localhost:5432/outreach"
    db_echo: bool = False

    #: Create the database if it is missing and apply migrations at startup.
    #: On for local development so a new person runs one command. Must be
    #: OFF in production: two instances starting together would migrate at
    #: the same time, and a bad migration should fail a deploy, not the app.
    auto_migrate: bool = True

    # ---- sources ---------------------------------------------------------
    #: A fine-grained token with NO scopes is enough - public data only. It
    #: raises the search limit from 10 requests per minute to 30, which is
    #: the difference between a usable run and a useless one.
    github_token: str = ""

    # ---- ranking ---------------------------------------------------------
    openai_api_key: str = ""
    #: 1536 dimensions, and cheap enough that ranking a few hundred results
    #: costs a fraction of a cent.
    embedding_model: str = "text-embedding-3-small"
    #: Reads one post and judges intent. A small, cheap model is enough:
    #: this is classification against a rubric, not reasoning.
    llm_model: str = "gpt-4o-mini"

    #: Writes the marketing plan. A bigger model than the classifier on
    #: purpose: judging one post against a rubric is easy, and writing a plan
    #: that is specific to one product rather than generic advice is not.
    #: One call per product, so the cost difference is a few cents a month.
    planner_model: str = "gpt-4o"

    #: How many of the best-embedding-ranked posts the triage reads.
    #:
    #: 0 means "all of them", which is what the triage was built for.
    #:
    #: ── Why 300, and what a smaller number costs ─────────────────────────
    #:
    #: It was 25, to cap tokens per run. Measured on one real GitHub search,
    #: same plan and the same 2,434 candidates both times:
    #:
    #:     pool 25    1 clear match,   2 results scoring 20+,  $0.0253
    #:     pool 300  14 clear matches, 4 results scoring 20+,  $0.0315
    #:
    #: Half a cent bought twice the usable results, and eight of the ten
    #: results at 25 scored 3 or less. The best score did not go up - this
    #: finds more leads, not better ones. The rest of this note is the
    #: earlier measurement that pointed the same way.
    #:
    #: On one run over 1,509 candidates, the ten results the full
    #: triage produced sat at these embedding ranks:
    #:
    #:     51, 105, 182, 141, 87, 169, 80, 3, 44, 57
    #:
    #: Only one is inside the top 25, and it is the weakest of the ten. The
    #: three best - 52, 47 and 46 - sit at ranks 51, 105 and 182, and a pool
    #: of 25 cuts all three.
    #:
    #: The cause is not a bad embedding model. Cosine similarity ranks by
    #: which words appear, so a shouty title carrying the product's exact
    #: vocabulary ranks 3rd while somebody describing the actual problem in
    #: their own words ranks 182nd. Closing that gap is the entire purpose of
    #: the triage, and capping the pool put it back.
    #:
    #: The cost being saved is smaller than the stage beside it. Every
    #: candidate is *already* embedded before this line is reached - that is
    #: how the ranking exists at all - and embedding a few thousand posts
    #: costs about what reading all their titles would. Capping here does not
    #: touch that spend; it only decides whether the money already spent on
    #: ordering gets used by something that can read.
    #:
    #: Judgements are cached by title, so the second run over the same
    #: repositories is nearly free whatever this is set to.
    #:
    #: If it has to be capped, a few hundred costs a fraction of a cent more
    #: than 25 and recovers most of what the ranks above show is lost.
    triage_pool: int = Field(default=300, ge=0)

    #: Keep only authors with no history in the repository they posted in.
    #:
    #: On, this removes roughly 80% of results - people writing tickets in
    #: their own project, who will fix the problem themselves rather than buy
    #: anything. Off, everything comes through and the score has to do the
    #: work on its own, which is worth testing: if the top 20 still looks
    #: right, the filter is redundant and you are seeing more.
    outsiders_only: bool = True

    #: Ignore issues in projects smaller than this.
    #:
    #: Phrase searches cover the whole of GitHub, so without it a run
    #: returns one-person side projects alongside the real ones.
    #: Commenting in a four-star repository reaches nobody. 500 keeps the
    #: established projects and removes the noise; 0 turns it off.
    min_repo_stars: int = 500
    #: Ignore Hacker News stories below this many points.
    #:
    #: The equivalent of `min_repo_stars`, and it applies to stories only.
    #: A story with two points sank without trace and replying to it reaches
    #: nobody. Comments are never filtered on it: Algolia reports `points:
    #: null` for every comment in the index, so judging them on that number
    #: would silently delete the better half of the source - and on Hacker
    #: News the comments are where somebody describes their actual problem.
    min_hn_points: int = 3
    #: Per source, per run. Not a target: a ceiling, so one run cannot spend
    #: the whole organisation's rate limit.
    source_max_requests: int = Field(default=40, ge=1)
    source_max_items: int = Field(default=1000, ge=1)
    source_max_seconds: float = Field(default=90.0, ge=5.0)

    # ---- crawling --------------------------------------------------------
    user_agent: str = "OutreachBot/0.1 (+https://example.com/bot)"
    http_timeout_seconds: float = 20.0

    crawl_max_pages: int = Field(default=500, ge=1)
    crawl_max_seconds: int = Field(default=900, ge=10)
    crawl_max_bytes: int = Field(default=100_000_000, ge=1_000)
    crawl_delay_seconds: float = Field(default=0.5, ge=0.0)
    thin_page_words: int = Field(default=120, ge=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
