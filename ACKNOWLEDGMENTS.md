# Acknowledgments

JARVIS is the result of collaboration between human engineers and multiple AI systems. Each contributor played a distinct role in the project's design, implementation, and evolution.

## Human Contributors

- **Coding Studio** ([@devghframework](https://github.com/devghframework)) — Project lead, architecture direction, feature requirements, code review, final merge decisions

## AI Collaborators

The project was built with a **collective intelligence** approach, drawing on the complementary strengths of multiple AI systems during architecture analysis, implementation, and review.

### Analysis & Design (Colligi² Collective Intelligence System)

During the architecture-analysis phase (March 2026), the project used the Colligi² multi-agent analysis system to generate, debate, and refine technical decisions. The following AI agents contributed opinions, proposals, and cross-evaluations:

- **OpenAI Codex** — Runtime strategy analysis, offline-first evaluation, local-model recommendations, cross-evaluation of Gemini/Claude/Ollama proposals
- **Anthropic Claude** — Memory budget analysis, Phase 0/1 implementation spec, conflict resolution, architecture debate
- **Google Gemini** — Tech stack evaluation, Korean NLP stack review, cross-agent reconciliation

Analysis artifacts preserved under `.projecthub/colligi2/workspace/` including `codex_proposal.md`, `codex_opinion.md`, and cross-evaluations (`codex_evaluation_of_*.md`, `*_evaluation_of_codex.md`).

### Implementation & Iteration

- **Claude Opus 4.6** (Anthropic) — Bulk of feature implementation during 2026-04 sessions: Web UI overhaul, Gemma 4 integration, Session Query Learning System, Repository viewer system, test suite, documentation. Attributed via `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>` trailers on commits.
- **Claude Sonnet 4.6** (Anthropic) — Early iteration on menu bar app, citation verification, governor safety controls.
- **OpenAI Codex** — Runtime architecture decisions, Python module structure guidance, offline-first design patterns reflected in the `alliance_*` implementation.

## Libraries & Models

JARVIS is built on top of many open-source libraries and models. See [README.md → Third-Party Model Licenses](README.md#third-party-model-licenses) for the full list with attributions.

## Note on GitHub Contributors Page

GitHub's Contributors page populates from commit authors whose email addresses are linked to GitHub accounts. AI collaborators like Codex and Claude don't have dedicated GitHub accounts, so their contributions are recorded through:

- `Co-Authored-By:` trailers in commit messages (visible in commit history)
- This `ACKNOWLEDGMENTS.md` file
- The Colligi² workspace artifacts preserved in `.projecthub/colligi2/`

To recognize AI contributions programmatically, search commit history:
```bash
git log --format="%B" | grep "Co-Authored-By:" | sort -u
```
