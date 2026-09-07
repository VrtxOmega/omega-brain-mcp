# September 7 review follow-up

Repairs cover the installed package and Docker dependency closure; explicitly task-scoped start/seal/handoff prompts and handoff resources; NAFE task attribution; event filtering before limits; and the public 512-dimensional representation contract.

Source receipts now include all tracked files (including data directories and tracked ignored files) plus nonignored, non-runtime untracked inputs. Git-ignored generated outputs do not invalidate the source-change gate. Non-Git folders use a conservative filesystem snapshot. Symlinks and submodules require an explicit packaged source snapshot. Python and Node must use this same source-selection contract.

Regression commands: `python -m pytest tests/ -v`; install the package and import it outside the checkout; build the Docker image and import its complete runtime as the non-root image user. These changes do not authenticate a remote caller, sandbox an administrator, or certify historical records. Live databases and recovery archives are not modified by this repository repair.
