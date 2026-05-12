"""Hacker News mention counts via Algolia. No auth required."""

from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import HackerNewsData, Result

ALGOLIA = "https://hn.algolia.com/api/v1/search"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
async def _search(client: httpx.AsyncClient, **params: Any) -> dict[str, Any]:
    r = await client.get(ALGOLIA, params=params, timeout=20.0)
    r.raise_for_status()
    return r.json()


async def _count_since(client: httpx.AsyncClient, query: str, since_epoch: int) -> int:
    body = await _search(
        client,
        query=query,
        tags="story",
        numericFilters=f"created_at_i>{since_epoch}",
        hitsPerPage=0,
    )
    return body.get("nbHits", 0)


async def collect_hn(company_name: str) -> Result[HackerNewsData]:
    now = int(time.time())
    ninety_days = now - 90 * 86400
    twelve_months = now - 365 * 86400

    async with httpx.AsyncClient() as client:
        try:
            mentions_90d = await _count_since(client, company_name, ninety_days)
            mentions_12mo = await _count_since(client, company_name, twelve_months)
            mentions_all = await _count_since(client, company_name, 0)

            top = await _search(
                client,
                query=company_name,
                tags="story",
                hitsPerPage=10,
            )

            stories = []
            for hit in (top.get("hits") or [])[:10]:
                stories.append(
                    {
                        "title": hit.get("title"),
                        "points": hit.get("points") or 0,
                        "comments": hit.get("num_comments") or 0,
                        "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                        "created_at": hit.get("created_at"),
                    }
                )
            stories.sort(key=lambda s: s["points"], reverse=True)
            top3 = stories[:3]

            return Result(
                success=True,
                data=HackerNewsData(
                    mentions_90d=mentions_90d,
                    mentions_12mo=mentions_12mo,
                    mentions_all_time=mentions_all,
                    top_stories=top3,
                ),
                source="hackernews",
            )
        except Exception as e:
            return Result(success=False, error=str(e), source="hackernews")
