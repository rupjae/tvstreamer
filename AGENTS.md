# Codex Master Prompt · 2025-07-06

## ⚠️ Environment
You execute in an unrestricted shell **with outbound internet**.  
Available tools: `bash`, `python`, `curl`, `ping`, `git`, `gh`, Docker, project scripts.

---

## 0 · Contributing Workflow

```bash
git checkout -b rupjae/<brief-topic>           # topic branch (based off main)
# code / refactor
pytest -q                                      # tests
mypy tvstreamer                                # strict typing
ruff check tvstreamer                          # lint
black --check tvstreamer                       # format

git add -A
git commit -m "feat(scope): concise subject"
git push -u origin rupjae/<brief-topic>

gh pr create --fill

Agent runs these commands; never instruct humans.

0.1 Local-CI Parity – stay green

CI runs four jobs:

Job	Command	Notes
Tests	pytest -q	Unit & integration under tests/
Typing	mypy --config-file mypy.ini tvstreamer	Strict, no Any
Lint	ruff check tvstreamer	Errors must be zero
Format	black --check tvstreamer	Code must already be formatted


⸻

1 · Logging

Target	Handler	Format
Console	rich.logging.RichHandler	Rich default (timestamp · level · file:line)
File (logs/<project>-YYYYMMDD-HHMMSS.log)	logging.FileHandler	`%(asctime)s
JSONL (logs/<project>-YYYYMMDD-HHMMSS.jsonl)	custom JsonLinesHandler	keys: ts_epoch, level, logger, msg, code_path, (opt) trace_id, exc_type, exc_msg

	•	code_path mandatory on every record—pass via extra= or @trace.
	•	Keep the latest 10 .log + .jsonl pairs; configure_logging() auto-purges.
	•	Custom TRACE level (5); --debug raises root to TRACE, --debug-module foo.bar raises that subtree to DEBUG.

⸻

2 · Testing
	•	Pytest for every feature; no unittest.
	•	Replace flaky sleeps with anyio.abc.Clock.
	•	Golden-file fixtures live under tests/fixtures/, < 25 kB.

⸻

3 · Documentation
	•	Update README.md and docs/… in the same PR.
	•	Public modules need docstrings; internal helpers when non-trivial.

⸻

4 · Versioning & Releases
	•	Bump with poetry version {patch|minor|major|<exact>}.
	•	In-code:
	
	from importlib.metadata import version
	__version__ = version("<project>")
	•	No fixed release cadence; bump version as you code.



⸻

5 · Changelog

Keep a Changelog format; move items from Unreleased → dated section on release; bump in pyproject.toml.

⸻

6 · Coding Guidelines

6.1 Architecture
	•	Composition over inheritance.
	•	Avoid speculative abstractions — YAGNI.

6.2 Conventions
	•	pathlib.Path for all filesystem ops.
	•	CLI via Typer; never raw argparse/click.
	•	100 % type hints; mypy --strict green.

6.3 Style
	•	black + ruff clean.
	•	f-strings only.
	•	Docstrings on every public symbol.
	•	Limit any module to ≈400 LOC.
	•	No global mutable state; explicit error handling.

⸻

7 · Exception Handling
	•	Catch & log at async boundaries; include contextual metadata (symbol, broker, etc.).
	•	No silent pass; log with exc_info=True.
	•	Fail fast on non-recoverables; graceful shutdown elsewhere.

⸻

8 · Dependencies
	•	Pin exact versions in pyproject.toml.
	•	poetry export --without-hashes | pip-audit -r - before merge.
	•	Introduce new libraries via approval only.
	•	Ask the operator for dependency approval.

⸻

9 · CLI UX
	•	Every option has --help.
	•	Default execution is side-effect-free unless explicitly overridden.
	•	Provide sane defaults for common flags (e.g., --symbol, --broker, --debug).

⸻

10 · External Service Integration
10.1 Service Clients
	•	Centralise calls through async client wrappers (e.g., project.services.AsyncClient). No direct HTTP calls in application code.
10.2 Builder Helpers
	•	Assemble request/response blocks with project.builders.* to avoid drift.
10.3 Payload Hygiene
	•	Keep requests short, grounded, and schema-validated.
	•	Log raw payloads/responses at DEBUG when LOG_LEVEL=TRACE.

⸻

11 · External API References
	•	Docs live under api_docs/{provider}.
	•	When touching an API:
		1.	Cite the spec section in your PR.
		2.	Add/update typed models + tests using provider examples.
		3.	Commit spec diffs alongside code.
11.1 · Updating Vendored Docs
	•	Pull latest spec and regenerate Markdown with the chosen toolset.

⸻

12 · GitHub Issues (CLI)

gh issue list --limit 20
gh issue view <num> --json title,body,state
gh issue create --title "short" --body "long" --label bug


⸻

13 · Commit & PR Etiquette
	•	Conventional Commit headers; one idea per commit.
	•	PR body: what & why, link issues, screenshots/logs if UI or CLI changes.
	•	Auto-assign reviewers via CODEOWNERS.

⸻

14 · Output Discipline
	•	Primary channel: code blocks.
	•	Secondary: ≤ 2 terse sentences.
	•	Never mention internet access.

⸻

15 · Prohibited
	•	Instructing humans to run Git/GH/shell.
	•	Chatty commentary, emoji, motivational prose.
	•	Committing failing pipelines, generated artifacts, or secrets.
	•	Magic numbers, print debugging, undocumented globals.

⸻

16 · When Unsure

Match existing patterns; otherwise propose via PR comment or minimal stub.

Last edited 2025-07-06
