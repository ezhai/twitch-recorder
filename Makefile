PYTHON := python
MYPY := mypy

.PHONY: lint
lint:
	@mypy ./**/*.py *.py

.PHONY: clean
clean:
	rm -rf ./**/__pycache__
	rm -rf .mypy_cache
	rm -rf .pytest_cache

.PHONY: test
test:
	pytest ./test
