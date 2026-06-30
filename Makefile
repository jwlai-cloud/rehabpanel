.PHONY: data baseline society benchmark demo test
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

demo:        ## launch the 3-panel demo UI
	python -m http.server --directory ui 8000
