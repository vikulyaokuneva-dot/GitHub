# AI Product Research Engine (Skeleton)

This is a standalone project for future product and niche research automation.

It is intentionally independent from `v3`:
- no imports from `v3`
- no shared pipeline usage
- separate folder, config, domain, pipeline, and artifacts

## Current Scope

Skeleton only, with stub logic:
- collect research input
- create seed niche candidates
- run stub demand/competition/economics/risk scoring
- build shortlist
- save artifacts

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

## Smoke Test

```bash
python -m unittest research_engine.tests.test_smoke
```
