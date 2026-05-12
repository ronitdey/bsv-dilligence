"""Pydantic schemas for the diligence pipeline."""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """Generic collector result wrapper. Never raises — always returns this."""

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    source: Optional[str] = None


class Company(BaseModel):
    name: str
    url: str
    github: Optional[str] = None
    portfolio: bool = False

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "_").replace(".", "")


class GitHubData(BaseModel):
    repo: str
    stars: int
    forks: int
    watchers: int
    open_issues: int
    created_at: Optional[str] = None
    pushed_at: Optional[str] = None
    avg_daily_stars: Optional[float] = None
    commits_90d: Optional[int] = None
    closed_issues_90d: Optional[int] = None
    contributor_count: Optional[int] = None
    median_first_response_hours: Optional[float] = None
    last_release_date: Optional[str] = None
    releases_90d: Optional[int] = None
    recent_issues: list[dict[str, Any]] = Field(default_factory=list)
    readme_excerpt: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None


class HackerNewsData(BaseModel):
    mentions_90d: int
    mentions_12mo: int
    mentions_all_time: int
    top_stories: list[dict[str, Any]] = Field(default_factory=list)


class PackageData(BaseModel):
    registry: str  # pypi | npm | crates
    package: str
    downloads_30d: Optional[int] = None
    downloads_90d: Optional[int] = None
    version_count: Optional[int] = None
    latest_version: Optional[str] = None


class WebData(BaseModel):
    homepage_text: Optional[str] = None
    funding_results: list[dict[str, Any]] = Field(default_factory=list)
    community_results: list[dict[str, Any]] = Field(default_factory=list)
    pricing_results: list[dict[str, Any]] = Field(default_factory=list)


class CollectionBundle(BaseModel):
    """Everything we collected about one company — what feeds the LLM."""

    company: Company
    github: Result[GitHubData]
    hn: Result[HackerNewsData]
    packages: list[Result[PackageData]] = Field(default_factory=list)
    web: Result[WebData]


class Scorecard(BaseModel):
    company: str
    one_line_pitch: str
    wedge: str
    icp: str

    wedge_clarity_score: int = Field(ge=1, le=10)
    wedge_clarity_reasoning: str

    pull_signals_score: int = Field(ge=1, le=10)
    pull_signals_reasoning: str

    defensibility_score: int = Field(ge=1, le=10)
    defensibility_reasoning: str

    bull_case: str
    bear_case: str
    what_would_change_ranking: str

    key_metrics: dict[str, Any] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


class RankEntry(BaseModel):
    rank: int
    company: str
    one_sentence_why: str
    top_signal: str
    biggest_risk: str


class Ranking(BaseModel):
    ranked_companies: list[RankEntry]
    methodology_note: str
    surprises: str
