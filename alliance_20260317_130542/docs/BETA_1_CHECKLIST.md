# JARVIS Beta 1 Checklist

## Completed

- Beta 1 scope fixed around core retrieval, export, safety, menu bar bridge, and basic voice
- Health checks stabilized and aligned with menu bar payload
- Push-to-talk microphone permission preflight added
- Parser runtime degradation behavior documented and tested
- Full Python test suite executed for Beta 1 cut
- Release notes and known issues documented
- Post-beta UI / voice backlog separated from Beta 1 scope

## Validation Result

- Full suite: `335 passed`
- Validation baseline uses the project `.venv` environment

## Remaining Before Tag / Archive

- Review dirty worktree for unrelated changes one final time
- Commit Beta 1 baseline
- Create release tag / archive artifact if needed
- Share known issues and deferred scope with internal testers

## Not Part of Beta 1

- Microphone device selector
- Avatar voice layer
- Mic input animation
- Final menu bar UI polish
- Live continuous voice UX
