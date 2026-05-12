"""CLI entrypoint. Orchestrates collection → analysis → ranking → output."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from .analysis import rank_companies, score_company
from .collectors import collect_github, collect_hn, collect_packages, collect_web
from .models import (
    CollectionBundle,
    Company,
    GitHubData,
    HackerNewsData,
    PackageData,
    Ranking,
    Result,
    Scorecard,
    WebData,
)
from .output import write_dashboard, write_memo

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_FILE = ROOT / "companies.json"
OUTPUT_DIR = ROOT / "output"
CACHE_DIR = OUTPUT_DIR / "cache"
SCORECARDS_DIR = OUTPUT_DIR / "scorecards"

console = Console()


def _ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SCORECARDS_DIR.mkdir(parents=True, exist_ok=True)


def _load_companies(only: Optional[str]) -> list[Company]:
    raw = json.loads(COMPANIES_FILE.read_text())
    companies = [Company(**c) for c in raw]
    if only:
        wanted = {n.strip().lower() for n in only.split(",") if n.strip()}
        companies = [c for c in companies if c.name.lower() in wanted]
        if not companies:
            console.print(f"[red]No companies matched --only '{only}'.[/red]")
            sys.exit(1)
    return companies


async def _collect_one(company: Company) -> CollectionBundle:
    gh_task = asyncio.create_task(collect_github(company.github))
    hn_task = asyncio.create_task(collect_hn(company.name))
    pkg_task = asyncio.create_task(collect_packages(company.name))
    web_task = asyncio.create_task(collect_web(company.name, company.url))

    gh, hn, pkgs, web = await asyncio.gather(gh_task, hn_task, pkg_task, web_task)

    return CollectionBundle(
        company=company,
        github=gh,
        hn=hn,
        packages=pkgs,
        web=web,
    )


def _cache_path(company: Company) -> Path:
    return CACHE_DIR / f"{company.slug}.raw.json"


def _save_cache(bundle: CollectionBundle) -> None:
    _cache_path(bundle.company).write_text(
        bundle.model_dump_json(indent=2), encoding="utf-8"
    )


def _load_cache(company: Company) -> Optional[CollectionBundle]:
    path = _cache_path(company)
    if not path.exists():
        return None
    try:
        return CollectionBundle.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


async def _run_collection(
    companies: list[Company], use_cache: bool, force_refresh: bool
) -> list[CollectionBundle]:
    bundles: list[CollectionBundle] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]Collecting[/bold] {task.fields[name]:24}"),
        BarColumn(bar_width=30, complete_style="green", finished_style="green"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("collect", total=len(companies), name="")
        for c in companies:
            progress.update(task, name=c.name)
            cached = None
            if use_cache and not force_refresh:
                cached = _load_cache(c)
            if cached is not None:
                bundles.append(cached)
                console.print(f"  [dim]· cached:[/dim] {c.name}")
            else:
                try:
                    bundle = await _collect_one(c)
                    _save_cache(bundle)
                    bundles.append(bundle)
                    _print_collection_summary(bundle)
                except Exception as e:
                    console.print(f"  [red]✗ {c.name}: {e}[/red]")
                    # Build an empty bundle so downstream still runs
                    bundles.append(
                        CollectionBundle(
                            company=c,
                            github=Result(success=False, error=str(e), source="github"),
                            hn=Result(success=False, error=str(e), source="hackernews"),
                            packages=[],
                            web=Result(success=False, error=str(e), source="web"),
                        )
                    )
            progress.advance(task)
    return bundles


def _print_collection_summary(bundle: CollectionBundle) -> None:
    parts = []
    if bundle.github.success and bundle.github.data:
        parts.append(f"gh {bundle.github.data.stars}★")
    elif bundle.company.github:
        parts.append("[red]gh failed[/red]")
    else:
        parts.append("[dim]gh n/a[/dim]")
    if bundle.hn.success and bundle.hn.data:
        parts.append(f"hn {bundle.hn.data.mentions_90d}/90d")
    else:
        parts.append("[dim]hn 0[/dim]")
    pkg_ok = sum(1 for r in bundle.packages if r.success)
    pkg_total = len(bundle.packages)
    if pkg_total:
        parts.append(f"pkg {pkg_ok}/{pkg_total}")
    if bundle.web.success:
        if bundle.web.data and bundle.web.data.homepage_text:
            parts.append(f"web {len(bundle.web.data.homepage_text)}c")
        else:
            parts.append("[dim]web sparse[/dim]")
    else:
        parts.append("[red]web failed[/red]")
    console.print(f"  [green]✓[/green] {bundle.company.name}: " + " · ".join(parts))


def _run_analysis(bundles: list[CollectionBundle]) -> list[Scorecard]:
    scorecards: list[Scorecard] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]Scoring[/bold]    {task.fields[name]:24}"),
        BarColumn(bar_width=30, complete_style="cyan", finished_style="cyan"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("score", total=len(bundles), name="")
        for b in bundles:
            progress.update(task, name=b.company.name)
            try:
                sc = score_company(b)
                scorecards.append(sc)
                _save_scorecard(b, sc)
                console.print(
                    f"  [green]✓[/green] {b.company.name}: "
                    f"wedge {sc.wedge_clarity_score} · pull {sc.pull_signals_score} · "
                    f"moat {sc.defensibility_score}"
                )
            except Exception as e:
                console.print(f"  [red]✗ {b.company.name}: {e}[/red]")
                traceback.print_exc()
            progress.advance(task)
    return scorecards


def _save_scorecard(bundle: CollectionBundle, scorecard: Scorecard) -> None:
    payload = {
        "scorecard": scorecard.model_dump(),
        "raw": bundle.model_dump(),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    out = SCORECARDS_DIR / f"{bundle.company.slug}.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _run_ranking(scorecards: list[Scorecard]) -> Ranking:
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]Ranking[/bold]    {task.fields[name]:24}"),
        BarColumn(bar_width=30, complete_style="magenta", finished_style="magenta"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("rank", total=1, name=f"{len(scorecards)} companies")
        ranking = rank_companies(scorecards)
        progress.advance(task)
    return ranking


def _final_summary(
    ranking: Ranking, scorecards: list[Scorecard], portfolio: list[Scorecard]
) -> None:
    table = Table(title="Final Ranking", show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Company")
    table.add_column("Rationale", overflow="fold")
    for e in ranking.ranked_companies:
        table.add_row(str(e.rank), e.company, e.one_sentence_why)
    console.print(table)

    if portfolio:
        console.print(
            f"\n[dim]Portfolio (excluded):[/dim] "
            + ", ".join(sc.company for sc in portfolio)
        )

    console.print(
        Panel.fit(
            f"[bold green]Outputs ready[/bold green]\n"
            f"  · memo:      [cyan]{OUTPUT_DIR / 'memo.md'}[/cyan]\n"
            f"  · dashboard: [cyan]{OUTPUT_DIR / 'dashboard.html'}[/cyan]\n"
            f"  · scorecards:[cyan] {SCORECARDS_DIR}[/cyan]",
            title="BSV Diligence",
            border_style="green",
        )
    )


RANKING_PATH = OUTPUT_DIR / "ranking.json"


def _save_ranking(ranking: Ranking) -> None:
    RANKING_PATH.write_text(ranking.model_dump_json(indent=2), encoding="utf-8")


def _load_ranking() -> Optional[Ranking]:
    if not RANKING_PATH.exists():
        return None
    try:
        return Ranking.model_validate_json(RANKING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_scorecards_from_disk(companies: list[Company]) -> list[tuple[Scorecard, Company, dict]]:
    """Load already-generated scorecards + raw bundle dicts for each company. Returns [] if any missing."""
    out: list[tuple[Scorecard, Company, dict]] = []
    for c in companies:
        path = SCORECARDS_DIR / f"{c.slug}.json"
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        sc = Scorecard.model_validate(payload["scorecard"])
        raw = payload.get("raw") or {}
        out.append((sc, c, raw))
    return out


@click.command()
@click.option("--only", default=None, help='Subset, e.g. --only "BAML,Atuin"')
@click.option(
    "--skip-collection",
    is_flag=True,
    help="Use cached raw data; re-run LLM analysis only.",
)
@click.option(
    "--rebuild-only",
    is_flag=True,
    help="Regenerate memo + dashboard from on-disk scorecards. Re-runs ranker once if ranking.json missing.",
)
@click.option("--no-cache", is_flag=True, help="Force fresh collection.")
def cli(
    only: Optional[str],
    skip_collection: bool,
    rebuild_only: bool,
    no_cache: bool,
) -> None:
    """BSV Diligence Agent — analyze 8 dev-tools companies and produce a ranked memo + dashboard."""
    load_dotenv()
    _ensure_dirs()

    if not os.environ.get("ANTHROPIC_API_KEY") and not rebuild_only:
        console.print("[red]ANTHROPIC_API_KEY not set. Copy .env.example to .env.[/red]")
        sys.exit(1)

    console.print(
        Panel.fit(
            "[bold]BSV Diligence Agent[/bold]\n"
            "Evaluating dev-tools companies for seed-stage investment.",
            border_style="green",
        )
    )

    companies = _load_companies(only)
    console.print(
        f"[dim]→ {len(companies)} companies: "
        + ", ".join(c.name for c in companies)
        + "[/dim]\n"
    )

    # ------- rebuild-only fast path -------
    if rebuild_only:
        loaded = _load_scorecards_from_disk(companies)
        if not loaded:
            console.print(
                "[red]--rebuild-only requires existing scorecards in output/scorecards/. "
                "Run without --rebuild-only first.[/red]"
            )
            sys.exit(1)
        scorecards = [t[0] for t in loaded]
        portfolio_scorecards = [sc for sc, c, _ in loaded if c.portfolio]
        competitive_scorecards = [sc for sc, c, _ in loaded if not c.portfolio]
        raw_by_company = {c.name: raw for _, c, raw in loaded}

        ranking = _load_ranking()
        if ranking is None and competitive_scorecards:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                console.print(
                    "[red]ranking.json not found; need ANTHROPIC_API_KEY to regenerate ranking once.[/red]"
                )
                sys.exit(1)
            console.print("[dim]No cached ranking; running ranker once...[/dim]")
            ranking = _run_ranking(competitive_scorecards)
            _save_ranking(ranking)
        elif ranking is None:
            ranking = Ranking(
                ranked_companies=[],
                methodology_note="No non-portfolio companies in this run.",
                surprises="N/A.",
            )
        else:
            console.print("[green]Loaded ranking.json from disk.[/green]")

        memo_path = OUTPUT_DIR / "memo.md"
        dash_path = OUTPUT_DIR / "dashboard.html"
        write_memo(memo_path, competitive_scorecards, portfolio_scorecards, ranking)
        write_dashboard(
            dash_path, competitive_scorecards, portfolio_scorecards, ranking,
            raw_by_company=raw_by_company,
        )
        console.print()
        _final_summary(ranking, competitive_scorecards, portfolio_scorecards)
        return

    # ------- normal path -------
    if skip_collection:
        bundles = []
        for c in companies:
            cached = _load_cache(c)
            if cached is None:
                console.print(f"[red]No cache for {c.name}; cannot --skip-collection.[/red]")
                sys.exit(1)
            bundles.append(cached)
        console.print("[green]Loaded all bundles from cache.[/green]\n")
    else:
        bundles = asyncio.run(
            _run_collection(companies, use_cache=not no_cache, force_refresh=no_cache)
        )

    console.print()
    scorecards = _run_analysis(bundles)

    if not scorecards:
        console.print("[red]No scorecards produced. Aborting.[/red]")
        sys.exit(1)

    portfolio_scorecards = [
        sc for sc, b in zip(scorecards, bundles) if b.company.portfolio
    ]
    competitive_scorecards = [
        sc for sc, b in zip(scorecards, bundles) if not b.company.portfolio
    ]

    console.print()
    if competitive_scorecards:
        ranking = _run_ranking(competitive_scorecards)
        _save_ranking(ranking)
    else:
        ranking = Ranking(
            ranked_companies=[],
            methodology_note="No non-portfolio companies in this run.",
            surprises="N/A.",
        )

    raw_by_company = {b.company.name: b.model_dump() for b in bundles}

    memo_path = OUTPUT_DIR / "memo.md"
    dash_path = OUTPUT_DIR / "dashboard.html"
    write_memo(memo_path, competitive_scorecards, portfolio_scorecards, ranking)
    write_dashboard(
        dash_path, competitive_scorecards, portfolio_scorecards, ranking,
        raw_by_company=raw_by_company,
    )

    console.print()
    _final_summary(ranking, competitive_scorecards, portfolio_scorecards)


if __name__ == "__main__":
    cli()
