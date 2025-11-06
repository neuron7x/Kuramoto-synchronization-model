install:
	pip install -r requirements.txt

test:
	pytest -q

lint:
	python -m pyflakes .

run-demo:
	python scripts/run_fhmc_demo.py
