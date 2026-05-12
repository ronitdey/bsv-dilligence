"""GitHub data collection. Tolerates missing token, repos, and rate limits."""

from __future__ import annotations

import base64
import os
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..models import GitHubData, Result

API = "https://api.github.com"


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bsv-diligence-agent",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


class _Transient(Exception):
    pass


@retry(
    retry=retry_if_exception_type(_Transient),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _get(client: httpx.AsyncClient, path: str, **params: Any) -> httpx.Response:
    r = await client.get(f"{API}{path}", headers=_headers(), params=params, timeout=30.0)
    if r.status_code in (502, 503, 504) or r.status_code == 429:
        raise _Transient(f"{r.status_code} {path}")
    return r


async def _fetch_readme(client: httpx.AsyncClient, repo: str) -> Optional[str]:
    try:
        r = await _get(client, f"/repos/{repo}/readme")
        if r.status_code != 200:
            return None
        body = r.json()
        content = body.get("content", "")
        if not content:
            return None
        decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
        return decoded[:3000]
    except Exception:
        return None


async def _commits_90d(client: httpx.AsyncClient, repo: str, since: datetime) -> Optional[int]:
    try:
        # Use per_page=1 and Link header pagination to get cheap total.
        r = await _get(
            client,
            f"/repos/{repo}/commits",
            since=since.isoformat(),
            per_page=1,
        )
        if r.status_code != 200:
            return None
        link = r.headers.get("Link", "")
        if 'rel="last"' in link:
            # Parse last page number from Link header.
            for part in link.split(","):
                if 'rel="last"' in part:
                    url = part.split(";")[0].strip().lstrip("<").rstrip(">")
                    if "page=" in url:
                        try:
                            return int(url.split("page=")[-1].split("&")[0])
                        except ValueError:
                            return None
        # Single page result
        data = r.json()
        return len(data) if isinstance(data, list) else None
    except Exception:
        return None


async def _contributor_count(client: httpx.AsyncClient, repo: str) -> Optional[int]:
    try:
        r = await _get(client, f"/repos/{repo}/contributors", per_page=1, anon="1")
        if r.status_code != 200:
            return None
        link = r.headers.get("Link", "")
        if 'rel="last"' in link:
            for part in link.split(","):
                if 'rel="last"' in part:
                    url = part.split(";")[0].strip().lstrip("<").rstrip(">")
                    if "page=" in url:
                        try:
                            return int(url.split("page=")[-1].split("&")[0])
                        except ValueError:
                            return None
        data = r.json()
        return len(data) if isinstance(data, list) else None
    except Exception:
        return None


async def _closed_issues_90d(client: httpx.AsyncClient, repo: str, since: datetime) -> Optional[int]:
    """Use the search API for an accurate count of closed issues since a date."""
    try:
        q = f"repo:{repo} is:issue is:closed closed:>={since.date().isoformat()}"
        r = await client.get(
            f"{API}/search/issues",
            headers=_headers(),
            params={"q": q, "per_page": 1},
            timeout=30.0,
        )
        if r.status_code != 200:
            return None
        return r.json().get("total_count")
    except Exception:
        return None


async def _releases(
    client: httpx.AsyncClient, repo: str, since: datetime
) -> tuple[Optional[str], Optional[int]]:
    try:
        r = await _get(client, f"/repos/{repo}/releases", per_page=30)
        if r.status_code != 200:
            return None, None
        releases = r.json()
        if not isinstance(releases, list) or not releases:
            return None, 0
        last = releases[0].get("published_at")
        count_90d = sum(
            1
            for rel in releases
            if rel.get("published_at")
            and datetime.fromisoformat(rel["published_at"].replace("Z", "+00:00")) >= since
        )
        return last, count_90d
    except Exception:
        return None, None


async def _recent_issues_with_response_times(
    client: httpx.AsyncClient, repo: str
) -> tuple[list[dict[str, Any]], Optional[float]]:
    """Return top-3 recent issue summaries + median first response hours (last 30d sample)."""
    try:
        r = await _get(
            client,
            f"/repos/{repo}/issues",
            state="all",
            per_page=20,
            sort="created",
            direction="desc",
        )
        if r.status_code != 200:
            return [], None
        issues = [i for i in r.json() if "pull_request" not in i][:20]
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        top3 = []
        for issue in issues[:3]:
            created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
            age_days = (now - created).days
            top3.append(
                {
                    "title": issue.get("title"),
                    "age_days": age_days,
                    "state": issue.get("state"),
                    "comments": issue.get("comments", 0),
                    "url": issue.get("html_url"),
                }
            )

        response_hours: list[float] = []
        for issue in issues:
            created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
            if created < thirty_days_ago:
                continue
            comments_url = issue.get("comments_url")
            if not comments_url or issue.get("comments", 0) == 0:
                continue
            try:
                cr = await client.get(
                    comments_url, headers=_headers(), params={"per_page": 1}, timeout=15.0
                )
                if cr.status_code != 200:
                    continue
                comments = cr.json()
                if comments and comments[0].get("created_at"):
                    first = datetime.fromisoformat(comments[0]["created_at"].replace("Z", "+00:00"))
                    hours = (first - created).total_seconds() / 3600
                    if hours >= 0:
                        response_hours.append(hours)
            except Exception:
                continue

        median = statistics.median(response_hours) if response_hours else None
        return top3, median
    except Exception:
        return [], None


async def collect_github(repo: Optional[str]) -> Result[GitHubData]:
    if not repo:
        return Result(success=False, error="no repo configured", source="github")

    async with httpx.AsyncClient() as client:
        try:
            r = await _get(client, f"/repos/{repo}")
        except Exception as e:
            return Result(success=False, error=f"repo lookup failed: {e}", source="github")

        if r.status_code == 404:
            return Result(success=False, error=f"repo {repo} not found (404)", source="github")
        if r.status_code != 200:
            return Result(
                success=False,
                error=f"repo lookup returned {r.status_code}",
                source="github",
            )

        info = r.json()
        created_at = info.get("created_at")
        now = datetime.now(timezone.utc)
        since_90d = now - timedelta(days=90)

        avg_daily_stars: Optional[float] = None
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days = max((now - created_dt).days, 1)
                avg_daily_stars = round(info.get("stargazers_count", 0) / age_days, 2)
            except Exception:
                pass

        commits_90d = await _commits_90d(client, repo, since_90d)
        contributors = await _contributor_count(client, repo)
        closed_issues_90d = await _closed_issues_90d(client, repo, since_90d)
        last_release, releases_90d = await _releases(client, repo, since_90d)
        top3, median_hours = await _recent_issues_with_response_times(client, repo)
        readme = await _fetch_readme(client, repo)

        data = GitHubData(
            repo=repo,
            stars=info.get("stargazers_count", 0),
            forks=info.get("forks_count", 0),
            watchers=info.get("subscribers_count", 0),
            open_issues=info.get("open_issues_count", 0),
            created_at=created_at,
            pushed_at=info.get("pushed_at"),
            avg_daily_stars=avg_daily_stars,
            commits_90d=commits_90d,
            closed_issues_90d=closed_issues_90d,
            contributor_count=contributors,
            median_first_response_hours=median_hours,
            last_release_date=last_release,
            releases_90d=releases_90d,
            recent_issues=top3,
            readme_excerpt=readme,
            description=info.get("description"),
            language=info.get("language"),
        )
        return Result(success=True, data=data, source="github")
