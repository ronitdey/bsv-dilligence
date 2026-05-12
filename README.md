# BSV Diligence Agent

An agent that evaluates 8 early-stage dev-tools companies in parallel and produces:
- Per-company JSON scorecards (`output/scorecards/*.json`)
- A ranked markdown memo (`output/memo.md`)
- A single-file HTML dashboard (`output/dashboard.html`)

Built for the Basis Set Ventures interview deliverable.

## Setup

```bash
cp .env.example .env  # fill in ANTHROPIC_API_KEY, GITHUB_TOKEN, TAVILY_API_KEY
uv sync
```

Required keys:
- `ANTHROPIC_API_KEY` — Claude Sonnet 4.5 for analysis and ranking
- `GITHUB_TOKEN` — raises rate limit from 60/hr to 5000/hr (a personal access token with `public_repo` scope is enough)
- `TAVILY_API_KEY` — web search; if absent, web collection is skipped gracefully

## Run

```bash
# Full run (all 8 companies)
uv run bsv-diligence

# Subset for iteration
uv run bsv-diligence --only "BAML,Atuin"

# Re-run LLM only against cached raw data
uv run bsv-diligence --skip-collection

# Force fresh collection (bypass cache)
uv run bsv-diligence --no-cache
```

Raw collected data is cached to `output/cache/{slug}.raw.json` so you can iterate on prompts without burning API quota.

## Architecture

```
src/
├── main.py              # CLI entrypoint (Click + Rich)
├── models.py            # Pydantic schemas (Result, Scorecard, Ranking)
├── collectors/          # GitHub, HN, packages, web — all async, all return Result[T]
├── analysis/            # Anthropic SDK wrapper, per-company scorer, final ranker
└── output/              # markdown memo + single-file HTML dashboard
```

Every collector returns a `Result[T]` with `success`, `data`, `error`. A single-company failure never aborts the run — it's logged and the LLM is told the signal is missing.

## Defaults & assumptions

- **Mem0** and **Rasa** are flagged as BSV portfolio in `companies.json`. They get scorecards but are excluded from the final ranking (the memo has a separate "Portfolio" section).
- The 3 companies without known repos (Parasail, Primitive, Entire) get a best-effort GitHub org discovery via web search and otherwise proceed without GitHub signals.
- HN searches collect raw mention counts; the LLM is responsible for disambiguating common-word names ("Entire", "Primitive") in its reasoning.
- Star history over 90 days uses average daily rate from creation date as the fallback when full stargazer pagination would be too expensive — this is noted in the memo's limitations appendix.
- LLM scorecard calls use a single-shot JSON output mode with one retry on parse failure.

## Outputs

After a run, check:
- `output/dashboard.html` — open in any browser (works on file://)
- `output/memo.md` — investment memo in markdown
- `output/scorecards/*.json` — raw structured analysis per company

## Limitations

- No direct access to Twitter, LinkedIn, Discord, or Reddit (only what surfaces via Tavily search).
- HN counts include false positives for common-word names.
- Funding info comes from web search snippets, not Crunchbase/PitchBook.
- Homepage scraping uses HTML parsing (selectolax); JS-rendered pages may return sparse text.
