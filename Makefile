PYTHON ?= python3
.PHONY: test release-plan release-build release-check release-prepare release-tests

test release-tests:
	$(PYTHON) -B -m unittest discover -s tests -v

release-plan:
	$(PYTHON) -B scripts/release.py plan

release-build:
	$(PYTHON) -B scripts/release.py build

release-check:
	$(PYTHON) -B scripts/release.py check

release-prepare:
	$(PYTHON) -B scripts/release.py prepare
