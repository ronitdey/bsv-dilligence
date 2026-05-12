"""Web collector — Tavily search + homepage scraping."""

from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Result, WebData

TAVILY_URL = "https://api.tavily.com/search"


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6), reraise=True)
async def _tavily(client: httpx.AsyncClient, api_key: str, query: str) -> list[dict[str, Any]]:
    r = await client.post(
        TAVILY_URL,
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": False,
        },
        timeout=30.0,
    )
    if r.status_code != 200:
        return []
    body = r.json()
    return [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": (r.get("content") or "")[:500],
        }
        for r in (body.get("results") or [])
    ]


async def _fetch_homepage(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(
            url,
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            },
        )
        if r.status_code != 200:
            return None
        tree = HTMLParser(r.text)
        for tag in tree.css("script, style, noscript, svg"):
            tag.decompose()
        text = tree.body.text(separator=" ", strip=True) if tree.body else tree.text()
        # Collapse whitespace
        text = " ".join(text.split())
        return text[:4000] if text else None
    except Exception:
        return None


async def collect_web(name: str, url: str) -> Result[WebData]:
    api_key = os.environ.get("TAVILY_API_KEY")
    domain = urlparse(url).netloc.replace("www.", "")

    async with httpx.AsyncClient() as client:
        homepage_text = await _fetch_homepage(client, url)

        funding: list[dict[str, Any]] = []
        community: list[dict[str, Any]] = []
        pricing: list[dict[str, Any]] = []

        if api_key:
            try:
                funding = await _tavily(client, api_key, f'"{name}" funding raised seed series')
            except Exception:
                funding = []
            try:
                community = await _tavily(client, api_key, f'"{name}" reddit OR "hacker news"')
            except Exception:
                community = []
            try:
                pricing = await _tavily(client, api_key, f"site:{domain} pricing")
            except Exception:
                pricing = []
        else:
            err = "TAVILY_API_KEY not set — skipping web search"
            if not homepage_text:
                return Result(success=False, error=err, source="web")
            return Result(
                success=True,
                data=WebData(homepage_text=homepage_text),
                error=err,
                source="web",
            )

        return Result(
            success=True,
            data=WebData(
                homepage_text=homepage_text,
                funding_results=funding,
                community_results=community,
                pricing_results=pricing,
            ),
            source="web",
        )
