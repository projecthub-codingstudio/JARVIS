# Contributing

Thank you for your interest in contributing to JARVIS! This guide will help you get set up and understand our development practices.

## Development Environment

### Prerequisites

- macOS on Apple Silicon (M1/M2/M3/M4)
- Python 3.12+
- Git

### Setup

```bash
git clone https://github.com/projecthub-codingstudio/JARVIS.git
cd JARVIS/alliance_20260317_130542

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Run the full test suite (357 tests)
python -m pytest tests/ -v
```

## Code Style

### Linting: ruff

```bash
# Check
ruff check src/ tests/

# Auto-fix
ruff check --fix src/ tests/
```

**Configuration** (in `pyproject.toml`):
- Python target: 3.12
- Line length: 100
- Rules: E, F, W, I, N, UP, B, A, SIM, TCH

### Type Checking: mypy

```bash
mypy src/jarvis/
```

- **Strict mode** enabled
- All public interfaces should be fully typed

## Testing

### Test Structure

```
tests/
├── contracts/       # Protocol, model, state validation
├── unit/            # Individual module tests
├── integration/     # Cross-module tests
├── e2e/             # End-to-end smoke tests
├── perf/            # Performance benchmarks
└── runtime/         # Runtime backend tests
```

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# By category
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v
python -m pytest tests/e2e/ -v

# By marker
python -m pytest -m slow -v          # Long-running tests
python -m pytest -m perf -v          # Performance benchmarks
python -m pytest -m integration -v   # Integration tests

# Single file
python -m pytest tests/unit/test_orchestrator.py -v
```

### Test Markers

| Marker | Description |
|--------|-------------|
| `slow` | Tests that take >5 seconds |
| `e2e` | End-to-end tests requiring full pipeline |
| `perf` | Performance benchmarks (50-query harness) |
| `integration` | Tests requiring database or multiple modules |

### Parser Dependency Tests

Some tests require optional parser libraries. If a library is not installed, related tests are **automatically skipped** (not failed):

```python
# Example: test auto-skips if pymupdf is not installed
pytest.importorskip("pymupdf")
```

## Project Structure

```
src/jarvis/
├── app/          # Bootstrap, config, runtime context
├── cli/          # User interfaces (REPL, menu bridge, voice)
├── contracts/    # ⚠️ Protocols, models, states, errors (FROZEN)
├── core/         # Orchestrator, governor, planner, tools
├── indexing/     # Parsers, chunker, file watcher
├── retrieval/    # FTS, vector, hybrid, evidence
├── runtime/      # MLX, Ollama, STT, TTS, embeddings
├── memory/       # Conversation store, task log
├── tools/        # read_file, search_files, draft_export
├── observability/ # Metrics, health, logging, tracing
└── perf/         # Benchmark harness
```

### Important: `contracts/` is Frozen

The `contracts/` directory contains 13 Protocol interfaces that were **frozen at Day 0**. Changes to these interfaces affect all downstream modules and require careful discussion.

If you need to modify a Protocol:
1. Open an issue describing the change and rationale
2. Assess impact on all implementing modules
3. Get approval before making changes

## Where to Contribute

### Good First Issues

Areas from [KNOWN_ISSUES_BETA_1.md](../docs/KNOWN_ISSUES_BETA_1.md) that welcome contributions:

| Area | Description | Difficulty |
|------|-------------|------------|
| Menu bar UI polish | Visual improvements to the SwiftUI menu bar | Medium |
| Voice UX | Animated mic feedback, waveform visualization | Medium |
| Citation verification | Improve claim-level citation matching | Hard |
| Parser coverage | Add new document format parsers | Easy-Medium |
| Test coverage | Expand unit/integration tests | Easy |

### Adding a New Parser

1. Create a parser function in `src/jarvis/indexing/parsers.py`
2. Register file extensions in the extension map
3. Handle encoding (UTF-8, CP949, UTF-16 LE)
4. Add tests in `tests/` (use `pytest.importorskip` for optional deps)
5. Update `pyproject.toml` if adding a new dependency

### Adding a New Tool

1. Implement the tool in `src/jarvis/tools/`
2. Register in `ToolRegistry` with appropriate permission level
3. Add to `ToolName` enum in `contracts/states.py` (requires Protocol discussion)
4. Add approval gate if the tool writes data

## Branch Strategy

- `main` — Stable release branch
- `feature/*` — Feature development branches
- PRs target `main`

## Commit Messages

Follow conventional commits:

```
feat: add PowerPoint parser support
fix: handle CP949 encoding in HWP files
docs: update retrieval pipeline wiki
test: add vector search integration test
refactor: extract chunking logic from index pipeline
```

## Related Pages

- [[Getting Started]] — Installation and first run
- [[Architecture Overview]] — System structure and module boundaries
- [[Design Decisions]] — Why things are the way they are

---

## :kr: 한국어

# 기여 가이드

JARVIS에 기여해주셔서 감사합니다! 이 가이드는 개발 환경 설정과 개발 관행을 안내합니다.

### 개발 환경 설정

```bash
git clone https://github.com/projecthub-codingstudio/JARVIS.git
cd JARVIS/alliance_20260317_130542
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v  # 335개 테스트 확인
```

### 코드 스타일

- **ruff**: 린터 + 포매터 (Python 3.12, 라인 100자)
- **mypy**: 정적 타입 체크 (strict 모드)

### 테스트

- 357개 테스트 (unit, integration, e2e, perf)
- 선택적 파서 의존성 누락 시 테스트 자동 스킵

### 기여 가능한 영역

| 영역 | 설명 | 난이도 |
|------|------|--------|
| 메뉴바 UI 폴리시 | SwiftUI 시각적 개선 | 중간 |
| 음성 UX | 마이크 피드백, 파형 시각화 | 중간 |
| 인용 검증 | claim 수준 인용 매칭 개선 | 어려움 |
| 파서 추가 | 새 문서 형식 파서 | 쉬움-중간 |
| 테스트 확장 | unit/integration 테스트 추가 | 쉬움 |

### 중요: `contracts/`는 동결됨

`contracts/` 디렉토리의 13개 Protocol 인터페이스는 **Day 0에 동결**되었습니다. 변경 시 이슈 생성 → 영향 평가 → 승인 필요.
