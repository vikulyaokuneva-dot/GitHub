# AI Product Research Engine (Skeleton)

This is a standalone project for future product and niche research automation.

It is intentionally independent from `v3`:
- no imports from `v3`
- no shared pipeline usage
- separate folder, config, domain, pipeline, and artifacts

## Current Scope

Skeleton only, with stub logic:
- collect research input from scenario config
- build stub niche universe
- generate candidate pool with scenario filters
- pass candidates to scoring stage placeholder
- save artifacts

## Input Scenarios

Pipeline uses scenario-based input:
- default config path: `research_engine/config/scenarios/default_research_scenario.json`
- loaded and validated by: `research_engine/config/research_input_loader.py`

Input parameters:
- `scenario_name`
- `budget_total`
- `target_price_min`
- `target_price_max`
- `target_margin_pct`
- `preferred_categories`
- `excluded_categories`
- `max_competition_level`
- `notes`

## Pipeline Stages

1. `research_input_stage`
2. `research_market_stage`
3. `research_scoring_stage`
4. `research_output_stage`

## Artifacts Produced

Saved into `research_engine/artifacts/`:
- `research_job.json`
- `research_input.json`
- `research_candidates.json`
- `research_summary.json`
- `research_report.txt`

## Run

```bash
python -m research_engine.entry
```

Optional custom scenario:

```bash
python -m research_engine.entry --scenario path/to/scenario.json
```

## Smoke Test

```bash
python -m unittest research_engine.tests.test_smoke
```
