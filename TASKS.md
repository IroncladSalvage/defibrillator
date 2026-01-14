# Defibrillator Task List

Repository manager for IroncladSalvage - the software salvage yard.

## Mission Alignment

Keep abandoned-but-essential software compiling with "Minimal Viable Maintenance":
- No new features, no refactors, no support tickets
- Prevent total bit-rot through automation
- Modern architectures (amd64, arm64), modern runtimes, LTS operating systems

## Phase 0 — Foundation

Build shared infrastructure first. Everything else depends on this.

- [ ] [#16](https://github.com/IroncladSalvage/defibrillator/issues/16) **Rate limit aware API calls**: Shared GitHub API utility with auth, pagination, ETag caching, backoff
- [ ] [#9](https://github.com/IroncladSalvage/defibrillator/issues/9) **License validator**: Verify `origin.license` matches actual LICENSE file

## Phase 1 — Minimal Viable Triage

High-signal, low-effort repo triage. Tells you what to ignore, watch, or touch.

- [ ] [#10](https://github.com/IroncladSalvage/defibrillator/issues/10) **Archive detector**: Check if upstream repos have been archived
- [ ] [#1](https://github.com/IroncladSalvage/defibrillator/issues/1) **Upstream monitoring**: Check if origin repos have new commits
- [ ] [#3](https://github.com/IroncladSalvage/defibrillator/issues/3) **Stale detection**: Flag repos where `last_touched` exceeds threshold
- [ ] [#12](https://github.com/IroncladSalvage/defibrillator/issues/12) **Stale report**: List repos approaching or exceeding staleness thresholds

## Phase 2 — Operational Visibility

Add more signals and consolidate into a dashboard.

- [ ] [#2](https://github.com/IroncladSalvage/defibrillator/issues/2) **CI status sync**: Fetch CI status from GitHub API and update YAML
- [ ] [#13](https://github.com/IroncladSalvage/defibrillator/issues/13) **Upstream divergence report**: Show how far behind upstream each fork is
- [ ] [#11](https://github.com/IroncladSalvage/defibrillator/issues/11) **Health dashboard**: Summary of repos by health status

## Phase 3 — Automation That Reduces Toil

Higher ROI automation, but requires stable validation and safety rails.

- [ ] [#8](https://github.com/IroncladSalvage/defibrillator/issues/8) **Fork automation script**: Create fork and populate YAML from upstream URL
- [ ] [#5](https://github.com/IroncladSalvage/defibrillator/issues/5) **Dependabot config generator**: Generate `.github/dependabot.yml` per language

## Phase 4 — Higher Complexity Features

More variance, more external dependencies. Implement when needed.

- [ ] [#14](https://github.com/IroncladSalvage/defibrillator/issues/14) **GHCR cleanup script**: Prune old container images
- [ ] [#15](https://github.com/IroncladSalvage/defibrillator/issues/15) **Artifact size monitor**: Track GitHub Actions artifact usage
- [ ] [#6](https://github.com/IroncladSalvage/defibrillator/issues/6) **Base image update checker**: Check if Docker base images are outdated
- [ ] [#7](https://github.com/IroncladSalvage/defibrillator/issues/7) **Runtime compatibility checker**: Verify repos work with latest runtimes
- [ ] [#4](https://github.com/IroncladSalvage/defibrillator/issues/4) **Security scanning integration**: Add workflow for security scans (depends on free-tier availability)

## Phase 5 — Nice-to-Have Publishing

Polish and external-facing features. Do once metrics are stable.

- [ ] [#18](https://github.com/IroncladSalvage/defibrillator/issues/18) **Badge generator**: Create status badges for README files
- [ ] [#17](https://github.com/IroncladSalvage/defibrillator/issues/17) **Changelog generator**: Generate changelog from commits
- [ ] [#19](https://github.com/IroncladSalvage/defibrillator/issues/19) **RSS/Atom feed**: Feed of repository status changes
