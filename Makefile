.PHONY: install test lint typecheck run-scenarios grade-local export-diagram demo-crash-resume demo-time-travel run-streamlit clean

install:
	pip install -e '.[dev,sqlite]'

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src --ignore-missing-imports

run-scenarios:
	python3 -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json

grade-local:
	python3 -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json

export-diagram:
	python3 -m langgraph_agent_lab.cli export-diagram --output outputs/graph_diagram.md

demo-crash-resume:
	python3 scripts/demo_crash_resume.py

demo-time-travel:
	python3 scripts/demo_time_travel.py

run-streamlit:
	LANGGRAPH_INTERRUPT=true streamlit run app/streamlit_app.py

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov dist build *.egg-info
	rm -f outputs/*.json outputs/*.db outputs/*.txt outputs/*.md
