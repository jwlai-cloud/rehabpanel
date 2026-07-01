.PHONY: data baseline society benchmark serve docker-build docker-run test
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

serve:       ## run the coordinator app backend (http://localhost:8000)
	uvicorn rehabpanel.api:app --reload --port 8000

docker-build: ## build the coordinator app container
	docker build -t rehabpanel .

docker-run:  ## run the container (http://localhost:8000); add -e DASHSCOPE_API_KEY for live Qwen
	docker run --rm -p 8000:8000 rehabpanel
