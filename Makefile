.PHONY: data baseline society benchmark ui demo video serve test
SEED ?= 7
RATIO ?= 1.3

data:        ## generate a seeded synthetic caseload
	python -m rehabpanel.generator --seed $(SEED) --ratio $(RATIO)

baseline:    ## single-agent scheduler
	python -m rehabpanel.baseline --seed $(SEED)

society:     ## multi-agent negotiation
	python -m rehabpanel.society.orchestrator --seed $(SEED)

benchmark:   ## baseline vs society across seeds + scarcity sweep
	python -m rehabpanel.benchmark

test:        ## lock the objective function
	pytest -q

ui:          ## bundle the latest run into ui/state.json for the demo
	python -m rehabpanel.ui_export

demo: ui     ## build ui state, then launch the 3-panel demo UI (http://localhost:8000)
	python -m http.server --directory ui 8000

video:       ## render the demo video -> results/demo.mp4 (macOS: say + ffmpeg + Chrome)
	bash scripts/make_video.sh

serve:       ## run the coordinator app backend (http://localhost:8000)
	uvicorn rehabpanel.api:app --reload --port 8000
