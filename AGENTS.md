# Agents

## Context

- Read org description: https://github.com/IroncladSalvage/.github/blob/master/profile/README.md

## Tasks

Find work using `gh`:

```bash
gh issue list --repo IroncladSalvage/defibrillator                # all open issues
gh issue list --repo IroncladSalvage/defibrillator --milestone "Phase 0: Foundation"  # by milestone
gh issue list --repo IroncladSalvage/defibrillator --label phase-0  # by label
gh issue view 16 --repo IroncladSalvage/defibrillator             # view specific issue
```

Milestones (in order):
- Phase 0: Foundation — shared infra, do first
- Phase 1: Minimal Triage — repo triage scripts
- Phase 2: Operational Visibility — dashboard/reports
- Phase 3: Toil Reduction — automation
- Phase 4: Complex Features — external deps
- Phase 5: Publishing — badges, feeds

Use the Oracle or other subagent to improve/design issues that lack important information before working on them.

Each task should have its own branch and pull request on the repo.

## Commands

Example:

```bash
uv sync
uv run python scripts/validate.py
uv run python scripts/generate_digest.py
```

## Rules

- **Python**: Always use `uv run python`, never `python` or `pip` directly
