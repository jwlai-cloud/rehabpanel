# Artifacts — one home for everything

Where each submission artifact lives and how to regenerate it.

## Committed (in the repo)

| Artifact | Path | Regenerate |
|---|---|---|
| Headline chart (gap vs scarcity) | `docs/assets/gap.png` | `make benchmark` |
| Coordinator app — Schedule/Negotiation | `docs/assets/app_schedule.png` | `make serve` |
| Coordinator app — KPIs (session timeline) | `docs/assets/app_kpis.png` | `make serve` |
| Coordinator app — Rules (causal weights) | `docs/assets/app_rules.png` | `make serve` |
| Architecture — engine + benchmark | `docs/architecture.svg` | `mmdc -i docs/architecture.mermaid` |
| Architecture — coordinator app | `docs/architecture_app.svg` | `mmdc -i docs/architecture_app.mermaid` |
| Design / spec / build record | `docs/*.md` | — |

## Generated locally (gitignored — regenerable, not in git)

| Artifact | Path | Regenerate |
|---|---|---|
| Demo video (~1:17, 11 scenes) | `results/demo.mp4` | `make video` |
| Benchmark metrics | `results/metrics.json` | `make benchmark` |
| Synthetic caseload | `data/*.json` | `make data` |
| UI snapshot state | `ui/state.json` | `make ui` |

> For the submission: upload `results/demo.mp4` to YouTube/Devpost and link it
> there (kept out of git to avoid binary churn as it's re-recorded). Run
> `make docker-build && make docker-run` for a live app, or deploy per
> `docs/deploy.md`.

## Hosted

| Artifact | Link | Note |
|---|---|---|
| Coordinator app (static snapshot) | https://claude.ai/code/artifact/c2508301-7480-4451-a792-ac9513f768d6 | the new 5-view app with **baked incident→replan states** (interactive, no backend); full live interactivity via `make serve` / `docs/deploy.md` |
| Public repo | https://github.com/jwlai-cloud/rehabpanel | MIT |
