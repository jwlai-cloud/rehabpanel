# RehabPanel — demo video script

~90s, 8 scenes. Narration = AI voice (macOS `say`, voice Samantha). Subtitles
burned in. Visuals = the clinical scrub UI (seed 7, ratio 1.3) + `results/gap.png`.
Rendered by `scripts/make_video.sh` → `results/demo.mp4`.

| # | Visual | Narration (= subtitle) |
|---|--------|------------------------|
| 1 | Title card | RehabPanel — a multi-agent society for rehab scheduling, running on Qwen Cloud. |
| 2 | Calendar, round 0 | A rehab nurse has 43 slots but 56 patients due. A single agent fills by acuity and abandons continuity — baseline value, minus 141. |
| 3 | Calendar, round 2 | Now the society negotiates. Five advocates raise objections; the charge-nurse referee resolves one conflict per round. |
| 4 | Calendar, round 4 | Each ruling moves a patient back to their primary clinician, and the plan's value climbs. |
| 5 | Calendar, round 6 | Every swap stays capacity-feasible. Continuity breaks fall from thirty toward thirteen. |
| 6 | Calendar, round 9 | After negotiation the value reaches minus 70 — a 71-point gain a single agent never finds. |
| 7 | gap.png chart | Across 25 runs the society wins every time, and the advantage grows as slots get scarcer. The conflict is the point. |
| 8 | Closing card | Decision support on synthetic data. All Qwen, deployed on Alibaba Cloud. |

Honest-scope line (scene 8) is mandatory: decision support, synthetic data.
