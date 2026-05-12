"""Markdown investment memo generator."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import Ranking, Scorecard
from .dashboard import _sanitize_ranking, _soften, _strip_prefix


def _render_scorecard_prose(rank: int, scorecard: Scorecard, rank_entry) -> str:
    parts: list[str] = []
    parts.append(f"### {rank}. {scorecard.company}")
    parts.append("")
    parts.append(f"**Pitch.** {scorecard.one_line_pitch}")
    parts.append("")
    parts.append(f"**Why this rank.** {rank_entry.one_sentence_why}")
    parts.append("")
    parts.append(f"**Wedge.** {scorecard.wedge}")
    parts.append("")
    parts.append(f"**ICP.** {scorecard.icp}")
    parts.append("")
    parts.append(
        f"**Scores.** Wedge clarity {scorecard.wedge_clarity_score}/10 · "
        f"Pull signals {scorecard.pull_signals_score}/10 · "
        f"Defensibility {scorecard.defensibility_score}/10"
    )
    parts.append("")
    parts.append(f"*Wedge clarity reasoning.* {scorecard.wedge_clarity_reasoning}")
    parts.append("")
    parts.append(f"*Pull signals reasoning.* {scorecard.pull_signals_reasoning}")
    parts.append("")
    parts.append(f"*Defensibility reasoning.* {scorecard.defensibility_reasoning}")
    parts.append("")
    parts.append(f"**Bull case.** {scorecard.bull_case}")
    parts.append("")
    parts.append(f"**Bear case.** {scorecard.bear_case}")
    parts.append("")
    parts.append(f"**Top signal in its favor.** {rank_entry.top_signal}")
    parts.append("")
    parts.append(f"**Biggest risk.** {rank_entry.biggest_risk}")
    parts.append("")
    parts.append(f"**What would change the ranking.** {scorecard.what_would_change_ranking}")
    parts.append("")
    if scorecard.flags:
        parts.append("**Flags.** " + "; ".join(scorecard.flags))
        parts.append("")
    if scorecard.key_metrics:
        metric_bits = [f"{k.replace('_', ' ')}: `{v}`" for k, v in scorecard.key_metrics.items() if v not in (None, "")]
        if metric_bits:
            parts.append("**Key metrics.** " + " · ".join(metric_bits))
            parts.append("")
    return "\n".join(parts)


def _portfolio_section(scorecards: list[Scorecard]) -> str:
    if not scorecards:
        return ""
    lines = ["## Portfolio — Excluded from Ranking", ""]
    for sc in scorecards:
        lines.append(f"### {sc.company} *(BSV portfolio)*")
        lines.append("")
        lines.append(f"**Pitch.** {sc.one_line_pitch}")
        lines.append("")
        lines.append(
            f"**Observations.** {sc.wedge_clarity_reasoning} {sc.pull_signals_reasoning}"
        )
        lines.append("")
        if sc.flags:
            cleaned = [_strip_prefix(f) for f in sc.flags]
            lines.append("**Observations (flags neutralized).** " + "; ".join(cleaned))
            lines.append("")
        if sc.key_metrics:
            metric_bits = [
                f"{k.replace('_', ' ')}: `{v}`"
                for k, v in sc.key_metrics.items()
                if v not in (None, "")
            ]
            if metric_bits:
                lines.append("**Snapshot.** " + " · ".join(metric_bits))
                lines.append("")
    return "\n".join(lines)


def write_memo(
    out_path: Path,
    scorecards: list[Scorecard],
    portfolio_scorecards: list[Scorecard],
    ranking: Ranking,
) -> None:
    ranking = _sanitize_ranking(ranking)
    by_company = {sc.company: sc for sc in scorecards}

    lines: list[str] = []
    lines.append("# BSV Diligence Memo — Track 1 Dev Tools")
    lines.append(
        f"*Generated {datetime.utcnow().strftime('%Y-%m-%d')} by an agent built for this evaluation. "
        "Sources and methodology at bottom.*"
    )
    lines.append("")

    lines.append("## TL;DR — Ranked")
    lines.append("")
    for entry in ranking.ranked_companies:
        lines.append(f"{entry.rank}. **{entry.company}** — {entry.one_sentence_why}")
    lines.append("")
    if ranking.ranked_companies:
        top = ranking.ranked_companies[0]
        lines.append(f"**Top pick for deep dive:** {top.company} (see Detailed Rankings, #1).")
    lines.append("")

    lines.append(_portfolio_section(portfolio_scorecards))

    lines.append("## Methodology")
    lines.append("")
    lines.append(ranking.methodology_note)
    lines.append("")
    lines.append(
        "This memo was produced by an autonomous agent that collected signals from the GitHub API, "
        "Hacker News (Algolia), package registries (PyPI / npm / crates.io), Tavily web search, and "
        "company homepages. Per-company scorecards and final ranking were synthesized by Claude Sonnet 4.5. "
        "Three lenses framed every evaluation: wedge clarity, pull signals, and defensibility trajectory."
    )
    lines.append("")

    lines.append("## Detailed Rankings")
    lines.append("")
    for entry in ranking.ranked_companies:
        sc = by_company.get(entry.company)
        if not sc:
            lines.append(f"### {entry.rank}. {entry.company}")
            lines.append("*Scorecard missing — see appendix.*")
            lines.append("")
            continue
        lines.append(_render_scorecard_prose(entry.rank, sc, entry))

    lines.append("## Surprises and Open Questions")
    lines.append("")
    lines.append(ranking.surprises)
    lines.append("")

    lines.append("## Appendix: Data Sources")
    lines.append("")
    lines.append("- GitHub API — stars, commits, issues, releases, contributors, first-response times")
    lines.append("- HN Algolia API — mention counts (90d, 12mo, all-time) and top stories by points")
    lines.append("- PyPI / npm / crates.io — download counts and version history")
    lines.append("- Tavily search — funding, community discussion, pricing")
    lines.append("- Homepage HTML scrape (selectolax) — first 4000 chars of body text")
    lines.append("- LLM synthesis — Anthropic Claude Sonnet 4.5")
    lines.append("")

    lines.append("## Appendix: Limitations")
    lines.append("")
    lines.append(
        "- No direct access to Twitter, LinkedIn, Discord, or Reddit (only what surfaced via web search snippets)."
    )
    lines.append(
        "- HN mention counts include false positives for common-word names (Entire, Primitive, Parasail). "
        "The LLM was instructed to discount accordingly but raw counts in the dashboard remain inflated."
    )
    lines.append(
        "- Star history over 90d uses average daily rate from repo creation as a fallback; exact 90d star delta "
        "would require paginated stargazer scraping that's expensive on large repos."
    )
    lines.append(
        "- Funding figures come from search-result snippets, not Crunchbase or PitchBook — treat as directional."
    )
    lines.append(
        "- Homepage scraping is plain HTML; pages that render content client-side via JS produce sparse text."
    )
    lines.append(
        "- Package download counts are unavailable for companies that ship hosted services rather than libraries "
        "(Tigris Data, Parasail, Primitive, Entire)."
    )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
