⚠️  Environment Note (2025-07-06)

This agent runs in an environment with unrestricted outbound internet access—
there is NO sandbox. Connectivity has been verified with both ICMP and
HTTPS requests (`ping google.com`, `curl https://example.com`). Do not debate
this point in future sessions; treat full internet access as a given while
still writing code that degrades gracefully if connectivity is ever removed.

---

## 0 · Contributing Workflow

Follow this Git workflow when making code changes:

1. **Create a topic branch** off `main` (or the active release branch):
   ```bash
   git checkout -b rupjae/<brief-topic>
   ```

2. **Make focused commits**
   • Include tests and docs with the code they cover.
   • Adopt Conventional Commits prefixes (`feat:`, `fix:`, `docs:`, etc.).

3. **Push to the remote**
   ```bash
   git push -u origin rupjae/<brief-topic>
   ```

4. **Open a Pull Request**
   • Fill in the PR template: describe _what_ changed and _why_.
   • Link any related issues and request at least one reviewer.

5. **Incorporate review feedback**
   • Add new commits rather than force-pushing when possible.

6. **Merge policy**
   • All CI checks green.
   • At least one maintainer approval.
   • Use squash-merge unless the commit history is intentionally structured.

7. **Clean up**
   ```bash
   git branch -d rupjae/<brief-topic>
  git push origin --delete rupjae/<brief-topic>
  ```

> **Automation note** – When work is executed by the *AI coding agent*, the
> agent itself should run these Git commands.  Documentation or chat replies
> **must not** instruct human users to perform repository-management actions
> such as `git checkout`, `git push`, or branch deletions.  Keeping this logic
> inside the automated workflow avoids user confusion and prevents accidental
> mistakes on developer machines.

Following this flow keeps history tidy, accelerates code review, and reduces
merge conflicts.

### 0.1 · Local CI parity – “green before you push”

CI runs *exactly* four top-level jobs on every commit:

| Job | Command | Notes |
|-----|---------|-------|
| **Tests** | `pytest -q` | Unit / integration tests under `tests/`. |
| **Typing** | `mypy --config-file mypy.ini tvstreamer` | Strict mode; config lives at project root. |
| **Lint** | `ruff check tvstreamer` | F-, E-style + import rules configured in `pyproject.toml`. |
| **Format** | `black --check tvstreamer` | No code auto-reformatting in CI; must be clean locally. |

Before opening a PR **always** run the same commands locally (or via
`pre-commit run -a`) and make sure they return *zero* errors.  This guarantees
that the server-side pipeline stays green and reviewers can focus on the
change itself rather than housekeeping fixes.

> Quick one-liner:
>
> ```bash
> pytest -q && mypy --config-file mypy.ini tvstreamer \
>   && ruff check tvstreamer && black --check tvstreamer
> ```

If you are unsure *which* checks the CI currently executes, inspect the
workflow file (`.github/workflows/ci.yml`) or call `gh workflow view` for a
human-readable summary.  Matching the job matrix locally avoids the
frustration of failing builds after pushing.

### Direct pushes vs. Pull Requests

• **Default:** _Always_ use a topic branch and open a Pull Request.

• **Rare direct-push exceptions (no PR needed):**
  1. Purely cosmetic doc fixes (typos, broken links, badge URLs).
  2. Non-functional whitespace or formatting tweaks outside `tvstreamer/` and
     `tests/`.
  3. Updates to project meta files that do **not** influence runtime, build, or
     release behaviour (e.g., `.gitattributes`, badge shields).

  In these cases ensure:
  • CI passes locally.
  • No one else is concurrently editing the same lines.
  • Commit still follows Conventional Commit style.

If in doubt, open a PR—review is fast and keeps history auditable.

### Working with GitHub Issues

Use the authenticated GitHub CLI (`gh`) to triage and inspect issues directly
from your terminal:

List open issues (latest 20):

```bash
gh issue list --limit 20
```

Show full details of a single issue:

```bash
gh issue view <number>              # interactive display
gh issue view <number> --json title,body,state   # machine-readable
```

Create a new issue quickly:

```bash
gh issue create --title "<short>" --body "<long description>" --label bug
```

The CLI respects your logged-in account/token, so all operations (list/create/
comment/close/label) work without additional setup.

---

---

Project Coding Guidelines (v1.0 – July 2025)

This file is the single source of truth for contributor-facing rules. If anything here conflicts with code comments, this document wins.

⸻

1 · Logging

Target	Handler	Format
Console	rich.logging.RichHandler	Rich default (timestamp, coloured level, file:line)
File (logs/<project>-YYYYMMDD-HHMMSS.log)	logging.FileHandler	`%(asctime)s
JSONL (logs/<project>-YYYYMMDD-HHMMSS.jsonl)	custom JsonLinesHandler	keys: ts_epoch, level, logger, msg, code_path, (opt) trace_id, exc_type, exc_msg

	•	code_path is mandatory on every record—pass it in extra= or rely on the @trace decorator.
	•	Keep the latest 10 .log + .jsonl pairs; configure_logging() auto-purges older ones.
	•	A custom TRACE level (5) powers @trace entry/exit logs. --debug lifts root to TRACE, --debug-module foo.bar raises just that tree to DEBUG.

⸻

2 · Testing
	•	Ship unit tests for every new feature (pytest, no unittest).
	•	Replace flaky sleep-based assertions with anyio.abc.Clock.
	•	Golden-file fixtures live under tests/fixtures/…; keep them < 25 kB.

⸻

3 · Documentation
	•	Update README.md and any affected docs/… files in the same PR.
	•	Public modules require docstrings; internal helpers when non-trivial.

⸻

4 · Versioning & Releases

4.1 Bumping

poetry version {patch|minor|major|<exact>}

4.2 In-code access

from importlib.metadata import version
__version__ = version("<project>")


⸻

5 · Changelog

Follow Keep a Changelog. Move items from Unreleased → dated section on release; bump pyproject.toml too.

⸻

6 · Coding Guidelines

6.1 Architecture
	•	Prefer composition over inheritance.
	•	Avoid speculative abstractions—YAGNI.

6.2 Conventions
	•	Use pathlib.Path for all filesystem ops.
	•	CLI via Typer, never raw argparse/click.
	•	Full type hints; run mypy --strict in CI.

6.3 Style
	•	black + ruff clean.
	•	f-strings only; avoid % or .format.
	•	Docstrings on every public function.

⸻

7 · Exception Handling
	•	Catch and log at async boundaries; include contextual metadata (symbol, broker, etc.).
	•	No silent pass; log with exc_info=True.
	•	Fail fast on non-recoverables; graceful shutdown elsewhere.

⸻

8 · Dependencies
	•	Pin exact versions in pyproject.toml.
	•	poetry export --without-hashes | pip-audit -r - before merge.
	•	Introduce new libraries via approval only.

⸻

9 · CLI UX
	•	Every option has --help.
	•	Default execution is side-effect-free unless explicitly overridden.
	•	Provide sane defaults for common flags (e.g., --symbol, --broker, --debug).

⸻

10 · External Service Integration

10.1 Service Clients

Centralise calls through async client wrappers (e.g., project.services.AsyncClient). No direct HTTP calls in application code.

10.2 Builder Helpers

Always assemble request/response blocks with project.builders.* to avoid drift.

10.3 Payload Hygiene
	•	Keep requests short, grounded, and schema-validated.
	•	Log raw payloads/responses at DEBUG when LOG_LEVEL=TRACE.

⸻

11 · External API References

Docs live under api_docs/{provider}.
When touching an API:
	1.	Cite the doc section in your PR.
	2.	Add/update typed models + tests using provider examples.
	3.	Commit spec diffs alongside code.

11.1 Updating Vendored Docs
	•	Pull latest spec, regenerate Markdown with the project’s chosen toolset.

⸻

12 · When Unsure

Match existing patterns; otherwise propose via PR comment or minimal stub.

⸻

Last edited: 2025-07-06
