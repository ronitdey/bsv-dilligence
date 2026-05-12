"""Final ranking step — takes the 6 non-portfolio scorecards and produces an ordered list."""

from __future__ import annotations

import json

from ..models import Ranking, Scorecard
from .llm import call_structured

SYSTEM = """You are a senior analyst at Basis Set Ventures producing the final ranking of seed-stage developer-tools companies you have analyzed.

You will receive a list of scorecards. Produce a strict ordering 1..N with NO TIES.

Your ranking should use prose-style judgment, not a numeric weighted sum. The three lens scores are inputs to your reasoning, but the final order is your call — backed by specific data points.

Each ranked entry needs:
- one_sentence_why: why this rank vs the company immediately above and below. Be specific. Avoid hedging.
- top_signal: the single strongest data point in this company's favor (a real number or fact, not a category)
- biggest_risk: the single biggest concern (concrete — not "competition")

Methodology note: 3-4 sentences on how you weighed the three lenses for THIS set of companies, including any meta-judgment (e.g., "I down-weighted HN signal because most of these have common-word name false positives").

Surprises: what was unexpected vs naive priors — companies that ranked higher or lower than category labels would suggest, signals that contradicted each other, etc.

Be opinionated. A VC reading this should know exactly where you stand."""


def rank_companies(scorecards: list[Scorecard]) -> Ranking:
    payload = [s.model_dump() for s in scorecards]
    user = (
        f"Here are {len(scorecards)} scorecards to rank (portfolio companies already excluded):\n\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        "Produce the ranking JSON now. Ensure ranks are 1..N with no ties."
    )
    return call_structured(SYSTEM, user, Ranking, max_tokens=4096)
