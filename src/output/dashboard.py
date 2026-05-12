"""Single-file HTML dashboard generator. Editorial / financial-terminal aesthetic."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..models import Ranking, Scorecard


ACCENT = "#d4ff4e"  # saturated chartreuse


CSS = """
:root {
  --bg: #0b0c0a;
  --bg-elev: #131512;
  --bg-card: #15171420;
  --ink: #ededeb;
  --ink-dim: #9a9c95;
  --ink-faint: #54574f;
  --rule: #2a2c27;
  --accent: %ACCENT%;
  --accent-dim: #d4ff4e22;
  --warn: #ff8a4c;
  --portfolio: #6b6e64;
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

.serif {
  font-family: "Fraunces", "Iowan Old Style", "Georgia", serif;
  font-feature-settings: "ss01", "ss02";
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

.page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 56px 40px 80px;
}

/* ---------- header ---------- */

.masthead {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  border-bottom: 1px solid var(--rule);
  padding-bottom: 28px;
  margin-bottom: 48px;
  gap: 32px;
  flex-wrap: wrap;
}
.masthead h1 {
  font-family: "Fraunces", "Iowan Old Style", Georgia, serif;
  font-weight: 400;
  font-size: 56px;
  letter-spacing: -0.02em;
  line-height: 1.0;
  margin: 0;
}
.masthead h1 .em { font-style: italic; color: var(--accent); }
.masthead .sub {
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-dim);
  margin-top: 14px;
  display: block;
}
.meta {
  text-align: right;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--ink-dim);
  line-height: 1.7;
  text-transform: uppercase;
}
.meta .v { color: var(--ink); font-variant-numeric: tabular-nums; }

/* ---------- section ---------- */

section { margin-bottom: 64px; }

.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--rule);
  padding-bottom: 12px;
  margin-bottom: 28px;
}
.section-head h2 {
  font-family: "Fraunces", Georgia, serif;
  font-weight: 400;
  font-size: 28px;
  letter-spacing: -0.01em;
  margin: 0;
}
.section-head .kicker {
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-dim);
}

/* ---------- card ---------- */

.card {
  border-top: 1px solid var(--rule);
  padding: 36px 0 36px;
  display: grid;
  grid-template-columns: 88px 1fr 320px;
  gap: 36px;
  position: relative;
}
.card:last-child { border-bottom: 1px solid var(--rule); }

.card.portfolio { opacity: 0.78; }

.rank {
  font-family: "Fraunces", Georgia, serif;
  font-size: 88px;
  font-weight: 300;
  font-variant-numeric: tabular-nums;
  line-height: 0.85;
  letter-spacing: -0.04em;
  color: var(--accent);
  position: relative;
}
.rank.top-pick::before {
  content: "";
  display: block;
  width: 32px;
  height: 1px;
  background: var(--accent);
  margin-bottom: 14px;
}
.rank .crown {
  display: block;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
  margin-top: 10px;
  font-weight: 500;
}
.card.portfolio .rank { color: var(--portfolio); font-size: 64px; padding-top: 8px; }

.body h3 {
  font-family: "Fraunces", Georgia, serif;
  font-weight: 500;
  font-size: 32px;
  letter-spacing: -0.015em;
  margin: 0 0 18px 0;
  line-height: 1.05;
}
.body .pitch {
  color: var(--ink-dim);
  font-size: 14px;
  margin-bottom: 22px;
  max-width: 60ch;
}

.dual-line {
  margin-bottom: 22px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 64ch;
}
.dual-line .line .lbl {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin-bottom: 4px;
}
.dual-line .line .val {
  font-size: 14px;
  line-height: 1.5;
  color: var(--ink);
}
.dual-line .line .val em {
  font-style: italic;
  color: var(--ink);
}
.flags {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.flag {
  display: inline-block;
  border: 1px solid var(--rule);
  color: var(--ink-dim);
  padding: 3px 9px;
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-radius: 2px;
}

.why-row {
  margin-top: 14px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  font-size: 13px;
}
.why-row .lbl {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin-bottom: 4px;
}
.why-row .val { color: var(--ink); line-height: 1.55; }
.why-row .val.warn { color: var(--warn); }

.expand-toggle {
  margin-top: 18px;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-dim);
  cursor: pointer;
  user-select: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  border: none;
  padding: 6px 0;
  font-family: inherit;
}
.expand-toggle:hover { color: var(--accent); }
.expand-toggle .chev { transition: transform 120ms ease; display: inline-block; }
.expand-toggle.open .chev { transform: rotate(90deg); }

.expanded {
  display: none;
  margin-top: 22px;
  padding: 24px;
  background: var(--bg-elev);
  border-left: 2px solid var(--accent);
}
.expanded.open { display: block; }
.expanded h4 {
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 6px 0;
}
.expanded h4:not(:first-child) { margin-top: 20px; }
.expanded p { margin: 0; color: var(--ink); line-height: 1.65; max-width: 75ch; }
.expanded .reasoning { color: var(--ink-dim); }

/* ---------- right rail: scores + metrics ---------- */

.rail {}
.scores { margin-bottom: 28px; }
.score-row {
  display: grid;
  grid-template-columns: 70px 1fr 38px;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-dim);
}
.score-row .label { white-space: nowrap; }
.score-row .bar {
  height: 4px;
  background: var(--rule);
  position: relative;
  overflow: hidden;
}
.score-row .bar .fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: var(--accent);
}
.score-row .num {
  font-family: "Fraunces", Georgia, serif;
  font-size: 22px;
  color: var(--ink);
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 400;
}
.card.portfolio .score-row .bar .fill { background: var(--portfolio); }

.metrics {
  border-top: 1px solid var(--rule);
  padding-top: 18px;
}
.metric {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 7px 0;
  border-bottom: 1px dashed var(--rule);
  font-size: 12px;
}
.metric:last-child { border-bottom: none; }
.metric .k {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-faint);
}
.metric .v {
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  font-weight: 500;
}
.metric .v.dim { color: var(--ink-faint); }
.metric .v .asterisk { color: var(--ink-faint); margin-left: 2px; font-size: 10px; vertical-align: super; }

.metric-note {
  margin-top: 14px;
  font-size: 10px;
  font-style: italic;
  color: var(--ink-faint);
  line-height: 1.5;
  max-width: 30ch;
}

/* portfolio observations — neutral framing, no flag-pill styling */
.observations { margin-top: 14px; max-width: 60ch; }
.observations .lbl {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin-bottom: 8px;
}
.observations ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.observations li {
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-dim);
  padding: 4px 0 4px 14px;
  position: relative;
}
.observations li::before {
  content: "·";
  position: absolute;
  left: 0;
  color: var(--portfolio);
}

/* ---------- methodology / surprises ---------- */

.note {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 36px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--ink-dim);
  border-top: 1px solid var(--rule);
  padding-top: 24px;
}
.note .kicker {
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--accent);
}
.note p { margin: 0 0 12px 0; max-width: 80ch; color: var(--ink); }

/* ---------- footer ---------- */

.footer {
  margin-top: 80px;
  border-top: 1px solid var(--rule);
  padding-top: 22px;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-faint);
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px;
}

@media (max-width: 900px) {
  .card { grid-template-columns: 56px 1fr; }
  .card .rail { grid-column: 1 / -1; }
  .why-row { grid-template-columns: 1fr; }
  .rank { font-size: 56px; }
  .masthead h1 { font-size: 36px; }
}
""".replace("%ACCENT%", ACCENT)


JS = """
document.addEventListener('click', (e) => {
  const t = e.target.closest('.expand-toggle');
  if (!t) return;
  const target = document.getElementById(t.dataset.target);
  if (!target) return;
  const isOpen = target.classList.toggle('open');
  t.classList.toggle('open', isOpen);
  t.querySelector('.label').textContent = isOpen ? 'Collapse' : 'Full scorecard';
});
"""


CONTAMINATED_HN = {"BAML", "Parasail", "Primitive", "Entire"}


def _fmt(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.1f}"
    return str(v)


def _fmt_downloads(n: Optional[int]) -> str:
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    return f"{n:,}"


def _downloads_from_raw(raw_packages: Optional[list[dict[str, Any]]]) -> Optional[int]:
    """Sum the last-30-day downloads across all successful package collectors."""
    if not raw_packages:
        return None
    total: Optional[int] = None
    for pkg in raw_packages:
        if not pkg or not pkg.get("success"):
            continue
        data = pkg.get("data") or {}
        d30 = data.get("downloads_30d")
        if d30 is None:
            continue
        total = (total or 0) + int(d30)
    return total


def _pick_metrics(
    sc: Scorecard,
    raw_packages: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Return a list of {label, value, dim, contaminated} dicts for the right-rail metrics."""
    m = sc.key_metrics or {}
    contaminated_company = sc.company in CONTAMINATED_HN

    def get(*keys: str) -> Any:
        for k in keys:
            if k in m and m[k] not in (None, ""):
                return m[k]
        return None

    downloads = get("downloads_30d")
    if downloads is None:
        downloads = _downloads_from_raw(raw_packages)

    items: list[tuple[str, Any, bool]] = [
        ("Stars", get("github_stars", "stars"), False),
        ("Commits / 90d", get("commits_90d"), False),
        ("Contributors", get("contributor_count", "contributors"), False),
        ("HN / 90d", get("hn_mentions_90d"), contaminated_company),
        ("HN / 12mo", get("hn_mentions_12mo"), contaminated_company),
        ("Downloads / 30d", downloads, False),
        ("Last release", get("last_release_date"), False),
    ]

    out = []
    for label, val, contaminated in items:
        if val is None:
            out.append({"label": label, "value": "—", "dim": True, "contaminated": False})
            continue
        # Trim ISO dates
        if isinstance(val, str) and "T" in val and len(val) > 10:
            val = val.split("T")[0]
        if label.startswith("Downloads"):
            value_str = _fmt_downloads(int(val) if isinstance(val, (int, float)) else int(str(val).replace(",", "")))
        else:
            value_str = _fmt(val)
        out.append(
            {
                "label": label,
                "value": value_str,
                "dim": bool(contaminated),
                "contaminated": bool(contaminated),
            }
        )
    return out


def _score_row(label: str, score: int) -> str:
    pct = max(0, min(10, score)) * 10
    return f"""
        <div class="score-row">
          <span class="label">{label}</span>
          <span class="bar"><span class="fill" style="width: {pct}%"></span></span>
          <span class="num">{score}</span>
        </div>
    """


def _strip_prefix(flag: str) -> str:
    """Strip a leading ALL_CAPS_OR_WORD: prefix from a portfolio flag string."""
    m = re.match(r"^[A-Z][A-Z0-9_ -]{1,32}:\s*(.+)$", flag)
    if m:
        rest = m.group(1)
        # Capitalize first letter of rest if it's lowercase
        return rest[0].upper() + rest[1:] if rest and rest[0].islower() else rest
    return flag


def _flag_pills(flags: list[str], portfolio: bool = False) -> str:
    """For competitive cards: pills. For portfolio cards: neutral 'Observations' list."""
    if not flags:
        return ""
    if portfolio:
        items = "".join(f"<li>{html.escape(_strip_prefix(f))}</li>" for f in flags)
        return f"""
          <div class="observations">
            <div class="lbl">Observations</div>
            <ul>{items}</ul>
          </div>
        """
    pills = "".join(f'<span class="flag">{html.escape(f)}</span>' for f in flags)
    return f'<div class="flags">{pills}</div>'


def _render_card(
    rank: Optional[int],
    sc: Scorecard,
    rank_entry,
    portfolio: bool,
    idx: int,
    raw_packages: Optional[list[dict[str, Any]]] = None,
) -> str:
    target_id = f"exp-{idx}"
    metrics = _pick_metrics(sc, raw_packages=raw_packages)
    has_contaminated = any(m["contaminated"] for m in metrics)

    metrics_rows = "".join(
        '<div class="metric"><span class="k">{label}</span>'
        '<span class="v{dim_cls}">{val}{aster}</span></div>'.format(
            label=html.escape(m["label"]),
            dim_cls=" dim" if m["dim"] else "",
            val=html.escape(m["value"]),
            aster='<span class="asterisk">*</span>' if m["contaminated"] else "",
        )
        for m in metrics
    )
    note_html = (
        '<div class="metric-note">* HN signal contaminated by common-word '
        "false positives; see methodology.</div>"
        if has_contaminated
        else ""
    )

    rank_display = str(rank) if rank is not None else "—"
    rank_class = "rank top-pick" if (rank == 1 and not portfolio) else "rank"
    crown_html = '<span class="crown">Top pick</span>' if rank == 1 and not portfolio else ""
    klass = "card portfolio" if portfolio else "card"

    why_block = ""
    if rank_entry is not None:
        why_block = f"""
          <div class="why-row">
            <div>
              <div class="lbl">Top signal</div>
              <div class="val">{html.escape(rank_entry.top_signal)}</div>
            </div>
            <div>
              <div class="lbl">Biggest risk</div>
              <div class="val warn">{html.escape(rank_entry.biggest_risk)}</div>
            </div>
          </div>
        """

    if rank_entry is not None:
        headline = f"""
          <div class="dual-line">
            <div class="line">
              <div class="lbl">Why this rank</div>
              <div class="val"><em>{html.escape(rank_entry.one_sentence_why)}</em></div>
            </div>
            <div class="line">
              <div class="lbl">What they do</div>
              <div class="val">{html.escape(sc.one_line_pitch)}</div>
            </div>
          </div>
        """
    else:
        # Portfolio cards: no rank_entry; only "What they do" + portfolio status note
        headline = f"""
          <div class="dual-line">
            <div class="line">
              <div class="lbl">What they do</div>
              <div class="val">{html.escape(sc.one_line_pitch)}</div>
            </div>
            <div class="line">
              <div class="lbl">Status</div>
              <div class="val">BSV portfolio — observational only. Excluded from competitive ranking.</div>
            </div>
          </div>
        """

    return f"""
      <article class="{klass}">
        <div class="{rank_class}">{rank_display}{crown_html}</div>
        <div class="body">
          <h3 class="serif">{html.escape(sc.company)}</h3>
          {headline}
          {why_block}
          {_flag_pills(sc.flags, portfolio=portfolio)}
          <button class="expand-toggle" data-target="{target_id}">
            <span class="chev">▸</span><span class="label">Full scorecard</span>
          </button>
          <div class="expanded" id="{target_id}">
            <h4>Wedge</h4>
            <p>{html.escape(sc.wedge)}</p>
            <h4>ICP</h4>
            <p>{html.escape(sc.icp)}</p>
            <h4>Wedge clarity ({sc.wedge_clarity_score}/10)</h4>
            <p class="reasoning">{html.escape(sc.wedge_clarity_reasoning)}</p>
            <h4>Pull signals ({sc.pull_signals_score}/10)</h4>
            <p class="reasoning">{html.escape(sc.pull_signals_reasoning)}</p>
            <h4>Defensibility ({sc.defensibility_score}/10)</h4>
            <p class="reasoning">{html.escape(sc.defensibility_reasoning)}</p>
            <h4>Bull case</h4>
            <p>{html.escape(sc.bull_case)}</p>
            <h4>Bear case</h4>
            <p>{html.escape(sc.bear_case)}</p>
            <h4>What would change the ranking</h4>
            <p>{html.escape(sc.what_would_change_ranking)}</p>
          </div>
        </div>
        <div class="rail">
          <div class="scores">
            {_score_row("Wedge", sc.wedge_clarity_score)}
            {_score_row("Pull", sc.pull_signals_score)}
            {_score_row("Moat", sc.defensibility_score)}
          </div>
          <div class="metrics">{metrics_rows}</div>
          {note_html}
        </div>
      </article>
    """


_SOFTEN_REPLACEMENTS: list[tuple[str, str]] = [
    ("fabricated social proof", "unverified marketing claims"),
    ("fabricated GitHub stars", "unverified GitHub star claims"),
    ("fabricated signals", "unverified signals"),
    ("fabricated", "unverified"),
    ("fake star count", "unverified star count"),
    ("fake GitHub stars", "unverified GitHub stars"),
    ("fake commit timestamps", "unverified commit timestamps"),
    ("fake commit activity timestamps", "unverified commit timestamps"),
    ("fake commit activity", "unverified commit activity"),
    ("appears to be vaporware", "shows no measurable developer traction"),
    ("is vaporware", "shows no measurable developer traction"),
    ("vaporware", "no measurable developer traction"),
    ("brazen fabrication", "unverified marketing claims"),
]


def _soften(text: Optional[str]) -> str:
    if not text:
        return text or ""
    out = text
    for needle, replacement in _SOFTEN_REPLACEMENTS:
        # Case-insensitive replace, preserving original casing only roughly
        out = re.sub(re.escape(needle), replacement, out, flags=re.IGNORECASE)
    return out


def _sanitize_ranking(ranking: Ranking) -> Ranking:
    """Apply softening to ranker output text so harsh LLM-generated phrasing never reaches the page."""
    entries = []
    for e in ranking.ranked_companies:
        entries.append(
            type(e)(
                rank=e.rank,
                company=e.company,
                one_sentence_why=_soften(e.one_sentence_why),
                top_signal=_soften(e.top_signal),
                biggest_risk=_soften(e.biggest_risk),
            )
        )
    return type(ranking)(
        ranked_companies=entries,
        methodology_note=_soften(ranking.methodology_note),
        surprises=_soften(ranking.surprises),
    )


def write_dashboard(
    out_path: Path,
    scorecards: list[Scorecard],
    portfolio_scorecards: list[Scorecard],
    ranking: Ranking,
    raw_by_company: Optional[dict[str, dict[str, Any]]] = None,
) -> None:
    by_company = {sc.company: sc for sc in scorecards}
    raw_by_company = raw_by_company or {}

    # Sanitize ranking text in case the LLM still used harsh language
    ranking = _sanitize_ranking(ranking)

    def _pkgs_for(name: str) -> Optional[list[dict[str, Any]]]:
        raw = raw_by_company.get(name) or {}
        return raw.get("packages")

    ranked_html = []
    idx = 0
    for entry in ranking.ranked_companies:
        sc = by_company.get(entry.company)
        if not sc:
            continue
        ranked_html.append(
            _render_card(
                entry.rank, sc, entry, portfolio=False, idx=idx,
                raw_packages=_pkgs_for(sc.company),
            )
        )
        idx += 1

    portfolio_html = []
    for sc in portfolio_scorecards:
        portfolio_html.append(
            _render_card(
                None, sc, None, portfolio=True, idx=idx,
                raw_packages=_pkgs_for(sc.company),
            )
        )
        idx += 1

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    n = len(scorecards)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BSV Diligence Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..600;1,9..144,300..600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="page">

  <header class="masthead">
    <div>
      <span class="sub">Basis Set Ventures · Track 1 Diligence</span>
      <h1 class="serif">Six dev-tools<br>companies, <span class="em">ranked.</span></h1>
    </div>
    <div class="meta">
      Generated <span class="v">{now}</span><br>
      Companies analyzed <span class="v">{n}</span><br>
      Ranked competitively <span class="v">{len(ranking.ranked_companies)}</span><br>
      Portfolio (observed) <span class="v">{len(portfolio_scorecards)}</span>
    </div>
  </header>

  <section>
    <div class="section-head">
      <h2 class="serif">Competitive ranking</h2>
      <span class="kicker">1 → {len(ranking.ranked_companies)} · no ties</span>
    </div>
    {"".join(ranked_html)}
  </section>

  <section>
    <div class="section-head">
      <h2 class="serif">Portfolio · observed only</h2>
      <span class="kicker">Excluded from ranking</span>
    </div>
    {"".join(portfolio_html) if portfolio_html else '<p style="color: var(--ink-dim)">None.</p>'}
  </section>

  <footer class="footer">
    <span>Methodology: Claude Sonnet 4.5 · Data: GitHub · HN Algolia · package registries · Tavily</span>
    <span>Generated {now}</span>
  </footer>

</div>
<script>{JS}</script>
</body>
</html>
"""
    out_path.write_text(page, encoding="utf-8")
