"""Generate a per-company Scorecard via Claude."""

from __future__ import annotations

import json
from typing import Any

from ..models import CollectionBundle, Scorecard
from .llm import call_structured


def _summarize_bundle(bundle: CollectionBundle) -> dict[str, Any]:
    """Compact dict of everything we collected, structured for the LLM."""
    out: dict[str, Any] = {
        "company": bundle.company.name,
        "url": bundle.company.url,
        "github_repo": bundle.company.github,
        "portfolio_company": bundle.company.portfolio,
    }

    if bundle.github.success and bundle.github.data:
        out["github"] = bundle.github.data.model_dump()
    else:
        out["github"] = {"missing": True, "reason": bundle.github.error}

    if bundle.hn.success and bundle.hn.data:
        out["hackernews"] = bundle.hn.data.model_dump()
    else:
        out["hackernews"] = {"missing": True, "reason": bundle.hn.error}

    packages = []
    for r in bundle.packages:
        if r.success and r.data:
            packages.append(r.data.model_dump())
        else:
            packages.append({"missing": True, "reason": r.error, "source": r.source})
    out["packages"] = packages

    if bundle.web.success and bundle.web.data:
        out["web"] = bundle.web.data.model_dump()
        if bundle.web.error:
            out["web"]["partial_note"] = bundle.web.error
    else:
        out["web"] = {"missing": True, "reason": bundle.web.error}

    return out


SYSTEM = """You are a senior analyst at Basis Set Ventures evaluating early-stage developer-tools companies for seed-stage investment.

You will produce a structured scorecard for ONE company based on collected signals. Be sharp, specific, and grounded in the data — no platitudes. If a signal is missing or weak, say so explicitly. Cite specific numbers from the data when reasoning.

Three lenses, each scored 1-10:
1. WEDGE CLARITY — Does this company solve a specific, painful job for a specific user? Is the ICP obvious? A vague "AI-powered platform for developers" scores low; a sharp "shell history sync for terminal power users" scores high.
2. PULL SIGNALS — Real, measurable demand: GitHub stars + velocity, commits, HN traction, downloads, community discussion. Distinguish push (marketing) from pull (users showing up).
3. DEFENSIBILITY TRAJECTORY — Will this still matter in 3 years? Network effects, data moats, ecosystem lock-in, sharp execution, hard technical problem, switching costs. Be skeptical of thin wrappers.

For HN mention counts, be careful with common-word names ("Entire", "Primitive", "Parasail") — many hits are false positives. Discount accordingly in your reasoning.

Be willing to give low scores (1-4) when warranted. Anchored scoring matters more than diplomacy."""


USER_TEMPLATE = """COMPANY: {name}
URL: {url}

SIGNALS (JSON):
{signals}

Produce a scorecard. Be specific about which data points drove each score. Flag risks honestly (single-founder team, crowded category, no repo visibility, common-name false positives, declining velocity, etc.).

Key metrics dict should include any of: github_stars, commits_90d, contributor_count, hn_mentions_90d, hn_mentions_12mo, downloads_30d, last_release_date — but only the ones that have real data (skip nulls).

Return JSON only."""


def score_company(bundle: CollectionBundle) -> Scorecard:
    signals = _summarize_bundle(bundle)
    user = USER_TEMPLATE.format(
        name=bundle.company.name,
        url=bundle.company.url,
        signals=json.dumps(signals, indent=2, default=str),
    )
    return call_structured(SYSTEM, user, Scorecard, max_tokens=4096)
