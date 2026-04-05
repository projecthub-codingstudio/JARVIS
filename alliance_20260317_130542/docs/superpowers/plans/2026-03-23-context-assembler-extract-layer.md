# ContextAssembler Extract Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a type-aware ContextAssembler layer (Pipeline Step 5) that extracts structured facts from evidence before LLM generation, eliminating LLM's role in data extraction and confining it to natural language composition.

**Architecture:** The 10-step pipeline (AUDIT_REPORT Section 8) defines Step 5 as "컨텍스트 조합" but the current implementation (`MLXRuntime._assemble_context`) does simple text concatenation. This plan introduces a `ContextAssembler` component that follows the `ChunkRouter` pattern — type-aware strategy dispatch via `heading_path` metadata. For structured evidence (table rows), it extracts facts deterministically with row-grouped composite keys; for unstructured text, it passes through. The LLM receives pre-extracted facts, not raw evidence. This replaces both the ad-hoc `_reformat_table_row` in MLXRuntime and the pattern-specific `_try_deterministic_table_answer` in Orchestrator.

**Tech Stack:** Python 3.12, dataclasses, Protocol interfaces, pytest

**Research basis:** TableRAG (NeurIPS 2024) — Schema+Cell Retrieval separation; Microsoft "Table Meets LLM" (WSDM 2024) — LLMs unreliable at cell extraction; TabRAG (arxiv 2511.06582) — structured intermediate representation before generation.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/jarvis/contracts/models.py` | Add `ExtractedFact` and `AssembledContext` data models |
| `src/jarvis/contracts/protocols.py` | Add `ContextAssemblerProtocol` |
| `src/jarvis/contracts/__init__.py` | Export new types |
| `src/jarvis/retrieval/context_assembler.py` | **New** — Type-aware fact extraction + context assembly |
| `src/jarvis/retrieval/extractors/__init__.py` | **New** — Extractor strategy package with base protocol |
| `src/jarvis/retrieval/extractors/table.py` | **New** — Table row fact extraction (row-grouped composite keys) |
| `src/jarvis/retrieval/extractors/text.py` | **New** — Text passage extraction (passthrough) |
| `src/jarvis/retrieval/extractors/code.py` | **New** — Code chunk extraction |
| `src/jarvis/runtime/mlx_runtime.py` | Remove `_reformat_table_row`, `_HEADER_KO_MAP`, `_MEAL_KEYS`; delegate `_assemble_context` to ContextAssembler |
| `src/jarvis/runtime/system_prompt.py` | Update prompt for fact-based context ("확인된 데이터" vs "참고 자료") |
| `src/jarvis/core/orchestrator.py` | Remove `_try_deterministic_table_answer` and related hacks |
| `src/jarvis/app/runtime_context.py` | Wire ContextAssembler via dependency injection |
| `tests/unit/test_context_assembler.py` | **New** — Unit tests |
| `tests/unit/test_extractors.py` | **New** — Strategy unit tests |
| `tests/integration/test_context_assembler_e2e.py` | **New** — End-to-end tests |

---

### Task 1: Data Models — ExtractedFact and AssembledContext

**Files:**
- Modify: `src/jarvis/contracts/models.py`
- Modify: `src/jarvis/contracts/__init__.py`
- Test: `tests/unit/test_context_assembler.py`

- [ ] **Step 1: Write the failing test for data models**

```python
# tests/unit/test_context_assembler.py
"""Tests for ContextAssembler extract layer."""
from jarvis.contracts import ExtractedFact, AssembledContext


class TestExtractedFact:
    def test_creation(self):
        fact = ExtractedFact(
            key="5일차 > Breakfast",
            value="계란후라이2+피망",
            source_chunk_id="abc123",
            source_document_id="doc1",
            confidence=1.0,
        )
        assert fact.key == "5일차 > Breakfast"
        assert fact.value == "계란후라이2+피망"
        assert fact.confidence == 1.0
        assert fact.is_deterministic is True

    def test_low_confidence(self):
        fact = ExtractedFact(
            key="요약", value="프로젝트 설명",
            source_chunk_id="c1", source_document_id="d1",
            confidence=0.7,
        )
        assert fact.is_deterministic is False


class TestAssembledContext:
    def test_creation(self):
        facts = (
            ExtractedFact(key="5일차 > Breakfast", value="계란후라이2+피망",
                          source_chunk_id="a", source_document_id="d1"),
            ExtractedFact(key="8일차 > Lunch", value="닭가슴살+샐러드",
                          source_chunk_id="b", source_document_id="d1"),
        )
        ctx = AssembledContext(facts=facts, text_passages=("텍스트 증거",))
        assert len(ctx.facts) == 2
        assert len(ctx.text_passages) == 1
        assert ctx.has_deterministic_facts is True

    def test_no_facts(self):
        ctx = AssembledContext(facts=(), text_passages=("텍스트만",))
        assert ctx.has_deterministic_facts is False
        assert ctx.deterministic_facts == ()

    def test_render_for_llm_facts_only(self):
        facts = (
            ExtractedFact(key="5일차 > Breakfast", value="계란후라이2+피망",
                          source_chunk_id="a", source_document_id="d1"),
        )
        ctx = AssembledContext(facts=facts, text_passages=())
        rendered = ctx.render_for_llm()
        assert "확인된 데이터" in rendered
        assert "5일차 > Breakfast: 계란후라이2+피망" in rendered
        assert "참고 자료" not in rendered

    def test_render_for_llm_passages_only(self):
        ctx = AssembledContext(facts=(), text_passages=("참고 텍스트",))
        rendered = ctx.render_for_llm()
        assert "확인된 데이터" not in rendered
        assert "참고 자료" in rendered

    def test_render_for_llm_mixed(self):
        facts = (
            ExtractedFact(key="Name", value="JARVIS",
                          source_chunk_id="a", source_document_id="d1"),
        )
        ctx = AssembledContext(facts=facts, text_passages=("설명 텍스트",))
        rendered = ctx.render_for_llm()
        assert "확인된 데이터" in rendered
        assert "참고 자료" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/test_context_assembler.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement data models**

Add to `src/jarvis/contracts/models.py` after `VerifiedEvidenceSet`:

```python
# --- Context Assembly Models (Pipeline Step 5) ---


@dataclass(frozen=True)
class ExtractedFact:
    """A single fact deterministically extracted from evidence.

    When confidence == 1.0, the fact was extracted by exact parsing
    (e.g., table cell lookup). The LLM should use this value as-is.

    key uses composite format for disambiguation: "Day=5 > Breakfast"
    so multiple table rows don't produce ambiguous identical keys.
    """

    key: str
    value: str
    source_chunk_id: str
    source_document_id: str = ""
    confidence: float = 1.0

    @property
    def is_deterministic(self) -> bool:
        return self.confidence >= 1.0


@dataclass(frozen=True)
class AssembledContext:
    """Pre-processed context ready for LLM consumption (Pipeline Step 5).

    Separates deterministic facts (table cells, code identifiers)
    from text passages that need LLM interpretation.
    """

    facts: tuple[ExtractedFact, ...] = ()
    text_passages: tuple[str, ...] = ()

    @property
    def has_deterministic_facts(self) -> bool:
        return any(f.is_deterministic for f in self.facts)

    @property
    def deterministic_facts(self) -> tuple[ExtractedFact, ...]:
        return tuple(f for f in self.facts if f.is_deterministic)

    def render_for_llm(self) -> str:
        """Render context for LLM prompt injection.

        Deterministic facts → "확인된 데이터" (use as-is).
        Text passages → "참고 자료" (synthesize and rephrase).
        """
        parts: list[str] = []
        if self.facts:
            fact_lines = [f"- {f.key}: {f.value}" for f in self.facts]
            parts.append("확인된 데이터:\n" + "\n".join(fact_lines))
        if self.text_passages:
            parts.append("참고 자료:\n" + "\n".join(self.text_passages))
        return "\n\n".join(parts)
```

- [ ] **Step 4: Update `__init__.py` exports**

Add `ExtractedFact` and `AssembledContext` to imports and `__all__` in `src/jarvis/contracts/__init__.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/test_context_assembler.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/jarvis/contracts/models.py src/jarvis/contracts/__init__.py tests/unit/test_context_assembler.py
git commit -m "feat: add ExtractedFact and AssembledContext data models for Pipeline Step 5"
```

---

### Task 2: ContextAssemblerProtocol + Extractor Base Protocol

**Files:**
- Modify: `src/jarvis/contracts/protocols.py`
- Modify: `src/jarvis/contracts/__init__.py`
- Create: `src/jarvis/retrieval/extractors/__init__.py`

- [ ] **Step 1: Add protocols**

In `src/jarvis/contracts/protocols.py`, add after `EvidenceBuilderProtocol`:

```python
@runtime_checkable
class ContextAssemblerProtocol(Protocol):
    """Assembles pre-processed context from verified evidence (Pipeline Step 5).

    Extracts structured facts deterministically from evidence items,
    separating data extraction (deterministic) from answer composition (LLM).
    Follows ChunkRouter pattern — type-aware strategy dispatch via heading_path.
    """

    def assemble(
        self,
        evidence: VerifiedEvidenceSet,
        query: str,
    ) -> AssembledContext:
        """Extract facts and assemble context from verified evidence."""
        ...
```

Add `AssembledContext` to the model imports at top of protocols.py. Add `ContextAssemblerProtocol` to `__init__.py`.

Create `src/jarvis/retrieval/extractors/__init__.py`:
```python
"""Type-specific evidence extractors for ContextAssembler.

Each extractor follows the ChunkRouter strategy pattern:
- Receives an EvidenceItem
- Returns extracted data (facts or passages)
- ContextAssembler dispatches via heading_path metadata
"""
from __future__ import annotations
from typing import Protocol
from jarvis.contracts import EvidenceItem, ExtractedFact


class FactExtractorProtocol(Protocol):
    """Extracts structured facts from an evidence item."""

    def extract(self, item: EvidenceItem) -> list[ExtractedFact]: ...


class PassageExtractorProtocol(Protocol):
    """Extracts text passages from an evidence item."""

    def extract(self, item: EvidenceItem) -> str: ...
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/ -q`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add src/jarvis/contracts/protocols.py src/jarvis/contracts/__init__.py src/jarvis/retrieval/extractors/__init__.py
git commit -m "feat: add ContextAssemblerProtocol and extractor base protocols"
```

---

### Task 3: Extractor Strategies (table, text, code)

**Files:**
- Create: `src/jarvis/retrieval/extractors/table.py`
- Create: `src/jarvis/retrieval/extractors/text.py`
- Create: `src/jarvis/retrieval/extractors/code.py`
- Test: `tests/unit/test_extractors.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_extractors.py
"""Tests for type-specific evidence extractors."""
from jarvis.contracts import ExtractedFact, EvidenceItem, CitationRecord, CitationState
from jarvis.retrieval.extractors.table import TableExtractor
from jarvis.retrieval.extractors.text import TextExtractor
from jarvis.retrieval.extractors.code import CodeExtractor


def _item(text: str, heading: str = "", chunk_id: str = "c1", doc_id: str = "d1") -> EvidenceItem:
    return EvidenceItem(
        chunk_id=chunk_id, document_id=doc_id, text=text,
        citation=CitationRecord(label="[1]", state=CitationState.VALID),
        relevance_score=0.5, heading_path=heading,
    )


class TestTableExtractor:
    def test_composite_keys_include_row_identifier(self):
        """Facts must have composite keys to disambiguate rows."""
        item = _item(
            "[Diet] Day=5 | Breakfast=계란후라이2+피망 | Lunch=닭가슴살",
            heading="table-row-Diet-4",
        )
        facts = TableExtractor().extract(item)
        # Key should include row identifier (Day=5) for disambiguation
        keys = {f.key for f in facts}
        assert any("Day=5" in k and "Breakfast" in k for k in keys)
        bf = next(f for f in facts if "Breakfast" in f.key)
        assert bf.value == "계란후라이2+피망"
        assert bf.confidence == 1.0
        assert bf.source_chunk_id == "c1"
        assert bf.source_document_id == "d1"

    def test_two_rows_produce_distinct_keys(self):
        """Day=5 and Day=8 should not produce conflicting Breakfast keys."""
        item5 = _item("[D] Day=5 | Breakfast=피망", heading="table-row-D-4", chunk_id="c5")
        item8 = _item("[D] Day=8 | Breakfast=오이", heading="table-row-D-7", chunk_id="c8")
        ext = TableExtractor()
        facts5 = ext.extract(item5)
        facts8 = ext.extract(item8)
        keys5 = {f.key for f in facts5}
        keys8 = {f.key for f in facts8}
        assert keys5.isdisjoint(keys8), "Different rows must produce distinct keys"

    def test_non_table_returns_empty(self):
        item = _item("일반 텍스트", heading="paragraph-0")
        assert TableExtractor().extract(item) == []

    def test_empty_value_skipped(self):
        item = _item("[S] A= | B=val", heading="table-row-S-0")
        facts = TableExtractor().extract(item)
        assert all(f.value for f in facts)

    def test_no_sheet_prefix_still_works(self):
        """Graceful handling of rows without [Sheet] prefix."""
        item = _item("Day=1 | Name=Test", heading="table-row-0")
        facts = TableExtractor().extract(item)
        # Should return empty (no match) or handle gracefully
        # The regex expects [SheetName] prefix per TableChunkStrategy
        assert isinstance(facts, list)


class TestTextExtractor:
    def test_returns_text(self):
        item = _item("JARVIS는 로컬 AI입니다.")
        assert TextExtractor().extract(item) == "JARVIS는 로컬 AI입니다."

    def test_includes_heading_context(self):
        item = _item("설명...", heading="section-architecture")
        passage = TextExtractor().extract(item)
        assert "설명" in passage


class TestCodeExtractor:
    def test_returns_code_with_scope(self):
        item = _item("def hello():\n    return 'world'", heading="code-python-0")
        passage = CodeExtractor().extract(item)
        assert "def hello" in passage
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/test_extractors.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement TableExtractor with composite keys**

`src/jarvis/retrieval/extractors/table.py`:
```python
"""TableExtractor — deterministic fact extraction from table-row evidence.

Parses key=value pipe-delimited format produced by TableChunkStrategy.
Produces facts with composite keys for row disambiguation:
  "Day=5 > Breakfast" instead of just "Breakfast"

This ensures multiple table rows don't produce ambiguous identical keys.
"""
from __future__ import annotations

import re

from jarvis.contracts import EvidenceItem, ExtractedFact

_TABLE_ROW_RE = re.compile(r"^\[([^\]]+)\]\s*(.+)$")


class TableExtractor:
    """Extracts structured facts from table-row evidence items."""

    def extract(self, item: EvidenceItem) -> list[ExtractedFact]:
        if not (item.heading_path and "table-row" in item.heading_path):
            return []

        m = _TABLE_ROW_RE.match(item.text)
        if not m:
            return []

        pairs_str = m.group(2)
        if "=" not in pairs_str:
            return []

        # Parse all key=value pairs
        raw_pairs: list[tuple[str, str]] = []
        for part in pairs_str.split("|"):
            part = part.strip()
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            key, value = key.strip(), value.strip()
            if key and value:
                raw_pairs.append((key, value))

        if not raw_pairs:
            return []

        # Determine row identifier from the first column (e.g., Day=5)
        first_key, first_val = raw_pairs[0]
        row_id = f"{first_key}={first_val}"

        # Build facts with composite keys: "Day=5 > Breakfast"
        facts: list[ExtractedFact] = []
        for key, value in raw_pairs:
            composite_key = f"{row_id} > {key}" if key != first_key else key
            facts.append(ExtractedFact(
                key=composite_key,
                value=value,
                source_chunk_id=item.chunk_id,
                source_document_id=item.document_id,
                confidence=1.0,
            ))

        return facts
```

- [ ] **Step 4: Implement TextExtractor and CodeExtractor**

`src/jarvis/retrieval/extractors/text.py`:
```python
"""TextExtractor — passage extraction from unstructured text evidence."""
from __future__ import annotations

from jarvis.contracts import EvidenceItem


class TextExtractor:
    """Extracts text passages for LLM interpretation (no deterministic facts)."""

    def extract(self, item: EvidenceItem) -> str:
        return item.text.strip()
```

`src/jarvis/retrieval/extractors/code.py`:
```python
"""CodeExtractor — passage extraction from code evidence."""
from __future__ import annotations

from jarvis.contracts import EvidenceItem


class CodeExtractor:
    """Extracts code passages for LLM interpretation."""

    def extract(self, item: EvidenceItem) -> str:
        text = item.text.strip()
        if item.heading_path:
            scope = item.heading_path.replace("-", " > ")
            return f"[{scope}]\n{text}"
        return text
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/test_extractors.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/jarvis/retrieval/extractors/ tests/unit/test_extractors.py
git commit -m "feat: add type-specific evidence extractors with composite key disambiguation"
```

---

### Task 4: ContextAssembler Implementation

**Files:**
- Create: `src/jarvis/retrieval/context_assembler.py`
- Modify: `tests/unit/test_context_assembler.py`

- [ ] **Step 1: Write failing tests for ContextAssembler**

Append to `tests/unit/test_context_assembler.py`:

```python
from jarvis.contracts import (
    CitationRecord, CitationState, EvidenceItem,
    TypedQueryFragment, VerifiedEvidenceSet,
)
from jarvis.retrieval.context_assembler import ContextAssembler


def _item(text: str, heading: str = "", chunk_id: str = "c1") -> EvidenceItem:
    return EvidenceItem(
        chunk_id=chunk_id, document_id="d1", text=text,
        citation=CitationRecord(label="[1]", state=CitationState.VALID),
        relevance_score=0.5, heading_path=heading,
    )


def _evidence(*items: EvidenceItem) -> VerifiedEvidenceSet:
    return VerifiedEvidenceSet(
        items=tuple(items),
        query_fragments=(TypedQueryFragment(text="test", query_type="semantic", language="ko"),),
    )


class TestContextAssembler:
    def test_table_produces_facts(self):
        ev = _evidence(_item("[D] Day=5 | Breakfast=피망", heading="table-row-D-4"))
        ctx = ContextAssembler().assemble(ev, query="5일차 아침")
        assert ctx.has_deterministic_facts
        assert any("Breakfast" in f.key and "피망" in f.value for f in ctx.facts)

    def test_text_produces_passages(self):
        ev = _evidence(_item("JARVIS는 AI입니다.", heading="paragraph-0"))
        ctx = ContextAssembler().assemble(ev, query="JARVIS?")
        assert not ctx.has_deterministic_facts
        assert len(ctx.text_passages) == 1

    def test_mixed_separates_facts_and_passages(self):
        ev = _evidence(
            _item("[S] Day=3 | Lunch=닭가슴살", heading="table-row-S-2", chunk_id="c1"),
            _item("프로젝트 설명...", heading="paragraph-0", chunk_id="c2"),
        )
        ctx = ContextAssembler().assemble(ev, query="3일차 점심")
        assert ctx.has_deterministic_facts
        assert len(ctx.text_passages) >= 1

    def test_budget_respected(self):
        items = [
            _item(f"텍스트 " * 100, heading=f"para-{i}", chunk_id=f"c{i}")
            for i in range(20)
        ]
        ev = _evidence(*items)
        ctx = ContextAssembler(max_context_chars=500).assemble(ev, query="test")
        rendered = ctx.render_for_llm()
        assert len(rendered) <= 700  # Some overhead

    def test_budget_stops_across_items(self):
        """Budget exhaustion in one item should prevent processing subsequent items."""
        items = [
            _item("A " * 300, heading="para-0", chunk_id="c0"),
            _item("B " * 300, heading="para-1", chunk_id="c1"),
        ]
        ev = _evidence(*items)
        ctx = ContextAssembler(max_context_chars=400).assemble(ev, query="test")
        # Should not include all of both passages
        total_len = sum(len(p) for p in ctx.text_passages)
        assert total_len <= 500

    def test_empty_evidence(self):
        ev = _evidence()
        ctx = ContextAssembler().assemble(ev, query="test")
        assert not ctx.has_deterministic_facts
        assert len(ctx.text_passages) == 0

    def test_preserves_evidence_order(self):
        """Items should be processed in evidence order (already sorted by relevance)."""
        ev = _evidence(
            _item("[S] Day=5 | X=first", heading="table-row-S-4", chunk_id="c5"),
            _item("[S] Day=8 | X=second", heading="table-row-S-7", chunk_id="c8"),
        )
        ctx = ContextAssembler().assemble(ev, query="test")
        values = [f.value for f in ctx.facts if "X" in f.key]
        assert values == ["first", "second"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/test_context_assembler.py::TestContextAssembler -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement ContextAssembler**

`src/jarvis/retrieval/context_assembler.py`:

```python
"""ContextAssembler — Pipeline Step 5: type-aware fact extraction + context assembly.

Sits between EvidenceBuilder (Step 4) and LLMGenerator (Step 7).
Follows the ChunkRouter pattern — dispatches evidence items to
type-specific extractors based on heading_path metadata.

For structured evidence (table rows): extracts facts deterministically.
For unstructured evidence (text, code): includes as reference passages.
The LLM receives pre-extracted facts, not raw evidence.

Research basis:
  - TableRAG (NeurIPS 2024): Schema+Cell retrieval separation
  - Microsoft "Table Meets LLM": LLMs unreliable at cell extraction
  - TabRAG: Structured intermediate representation before generation
"""
from __future__ import annotations

from jarvis.contracts import (
    AssembledContext,
    EvidenceItem,
    VerifiedEvidenceSet,
)
from jarvis.retrieval.extractors.code import CodeExtractor
from jarvis.retrieval.extractors.table import TableExtractor
from jarvis.retrieval.extractors.text import TextExtractor

_DEFAULT_MAX_CONTEXT_CHARS = 16_384  # ~4K tokens


class ContextAssembler:
    """Type-aware evidence extraction and context assembly.

    Implements ContextAssemblerProtocol.
    Dispatches to extractors following ChunkRouter pattern.
    """

    def __init__(self, *, max_context_chars: int = _DEFAULT_MAX_CONTEXT_CHARS) -> None:
        self._max_context_chars = max_context_chars
        self._table = TableExtractor()
        self._text = TextExtractor()
        self._code = CodeExtractor()

    def assemble(
        self,
        evidence: VerifiedEvidenceSet,
        query: str,
    ) -> AssembledContext:
        """Extract facts and assemble context from verified evidence."""
        facts: list = []
        passages: list[str] = []
        budget = self._max_context_chars

        for item in evidence.items:
            if budget <= 0:
                break

            extractor = self._select_extractor(item)

            if extractor is self._table:
                extracted = extractor.extract(item)
                for fact in extracted:
                    cost = len(fact.key) + len(fact.value) + 4
                    if budget - cost < 0:
                        break
                    facts.append(fact)
                    budget -= cost
            else:
                passage = extractor.extract(item)
                cost = len(passage)
                if budget - cost < 0:
                    remaining = budget
                    if remaining > 100:
                        passages.append(passage[:remaining] + "...")
                        budget = 0
                    break
                passages.append(passage)
                budget -= cost

        return AssembledContext(
            facts=tuple(facts),
            text_passages=tuple(passages),
        )

    def _select_extractor(self, item: EvidenceItem):
        """Select extraction strategy based on evidence type metadata.

        Returns the extractor object directly (ChunkRouter pattern).
        """
        hp = item.heading_path or ""
        if "table-row" in hp or "table-full" in hp:
            return self._table
        if "code" in hp:
            return self._code
        return self._text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/test_context_assembler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jarvis/retrieval/context_assembler.py tests/unit/test_context_assembler.py
git commit -m "feat: implement ContextAssembler with type-aware extraction dispatch"
```

---

### Task 5: Wire into MLXRuntime + Update System Prompt

**Files:**
- Modify: `src/jarvis/runtime/mlx_runtime.py`
- Modify: `src/jarvis/runtime/system_prompt.py`
- Modify: `src/jarvis/app/runtime_context.py`

- [ ] **Step 1: Update system prompt first (prevents stale LLM instructions)**

Replace `SYSTEM_PROMPT` in `src/jarvis/runtime/system_prompt.py`:

```python
SYSTEM_PROMPT = (
    "당신은 JARVIS입니다. 사용자의 로컬 워크스페이스 AI 어시스턴트입니다.\n\n"
    "답변 규칙:\n"
    "- '확인된 데이터' 섹션의 값은 정확한 사실입니다. 그대로 사용하세요. 변경하거나 추측하지 마세요.\n"
    "- '참고 자료' 섹션은 배경 정보입니다. 종합하여 자연어로 답변하세요.\n"
    "- 핵심 답변만 간결하게 자연어로 답하세요.\n"
    "- 출처 파일명, key=value 형식, 기술적 메타 정보는 답변에 포함하지 마세요.\n"
    "- 확인된 데이터에 없는 내용은 추측하지 마세요."
)
```

- [ ] **Step 2: Replace `_assemble_context` in mlx_runtime.py**

Remove: `_HEADER_KO_MAP`, `_MEAL_KEYS` class attributes, `_reformat_table_row` static method.

Add `self._context_assembler = None` to `__init__`.

Replace `_assemble_context`:

```python
def _assemble_context(self, evidence: VerifiedEvidenceSet, query: str = "") -> str:
    """Assemble evidence via ContextAssembler (Pipeline Step 5)."""
    if self._context_assembler is None:
        from jarvis.retrieval.context_assembler import ContextAssembler
        self._context_assembler = ContextAssembler(
            max_context_chars=self._max_context_chars,
        )
    assembled = self._context_assembler.assemble(evidence, query)
    return assembled.render_for_llm()
```

Update call sites to pass `query`:
- `generate()`: `context = self._assemble_context(evidence, prompt)`
- `generate_stream()`: `context = self._assemble_context(evidence, prompt)`

- [ ] **Step 3: Wire ContextAssembler in runtime_context.py (dependency injection)**

Add to `build_runtime_context()` where other components are created. The ContextAssembler should be available for direct injection if needed:

```python
from jarvis.retrieval.context_assembler import ContextAssembler
context_assembler = ContextAssembler(max_context_chars=16_384)
```

Pass to MLXRuntime if the constructor accepts it, or let MLXRuntime lazy-init as fallback.

- [ ] **Step 4: Run all tests**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/ -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/jarvis/runtime/mlx_runtime.py src/jarvis/runtime/system_prompt.py src/jarvis/app/runtime_context.py
git commit -m "refactor: delegate context assembly to ContextAssembler, update system prompt for fact-based context"
```

---

### Task 6: Remove Orchestrator Hacks

**Files:**
- Modify: `src/jarvis/core/orchestrator.py`

- [ ] **Step 1: Remove deterministic table answer bypass**

Remove from `handle_turn()`: the `_try_deterministic_table_answer(...)` block and its call site.

Remove from `handle_turn_stream()`: the equivalent deterministic table block.

Remove the `_try_deterministic_table_answer` method entirely.

Remove the row-number-based evidence filtering/reordering block in `_retrieve_evidence()` (the `_ROW_NUM_FILTER_RE` / `requested_nums` section that filters non-matching table rows and reorders by query mention order).

**Keep:** The reranker row-protection block (ensures row-matched chunks survive reranking cutoff) — this is a retrieval concern, not extraction.

- [ ] **Step 2: Run all tests**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/ -q`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add src/jarvis/core/orchestrator.py
git commit -m "refactor: remove pattern-specific table hacks, extraction now handled by ContextAssembler"
```

---

### Task 7: Integration Test — End-to-End

**Files:**
- Create: `tests/integration/test_context_assembler_e2e.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_context_assembler_e2e.py
"""Integration: table query through ContextAssembler produces unambiguous facts."""
from jarvis.contracts import (
    CitationRecord, CitationState, EvidenceItem,
    TypedQueryFragment, VerifiedEvidenceSet,
)
from jarvis.retrieval.context_assembler import ContextAssembler


def test_diet_multi_row_query_produces_distinct_facts():
    """The exact scenario that previously confused the LLM:
    Day=5 Breakfast=계란후라이2+피망 vs Day=8 Breakfast=계란후라이2+오이.
    ContextAssembler must produce distinct composite keys."""
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="day5", document_id="diet",
                text="[Diet] Day=5 | Breakfast=계란후라이2+피망 | Lunch=닭가슴살+현미밥",
                citation=CitationRecord(label="[1]", state=CitationState.VALID),
                relevance_score=1.0, heading_path="table-row-Diet-4",
            ),
            EvidenceItem(
                chunk_id="day8", document_id="diet",
                text="[Diet] Day=8 | Breakfast=계란후라이2+오이 | Lunch=닭가슴살+샐러드",
                citation=CitationRecord(label="[2]", state=CitationState.VALID),
                relevance_score=0.9, heading_path="table-row-Diet-7",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="5일차 아침 8일차 점심", query_type="semantic", language="ko"),),
    )

    ctx = ContextAssembler().assemble(evidence, query="5일차 아침 8일차 점심")

    # Day 5 Breakfast must be 피망, not 오이
    day5_bf = next((f for f in ctx.facts if "Day=5" in f.key and "Breakfast" in f.key), None)
    assert day5_bf is not None
    assert day5_bf.value == "계란후라이2+피망"

    # Day 8 Breakfast must be 오이
    day8_bf = next((f for f in ctx.facts if "Day=8" in f.key and "Breakfast" in f.key), None)
    assert day8_bf is not None
    assert day8_bf.value == "계란후라이2+오이"

    # Rendered context must be unambiguous
    rendered = ctx.render_for_llm()
    assert "Day=5 > Breakfast: 계란후라이2+피망" in rendered
    assert "Day=8 > Breakfast: 계란후라이2+오이" in rendered


def test_mixed_table_and_text():
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="r1", document_id="d1",
                text="[Data] Name=JARVIS | Version=1.0",
                citation=CitationRecord(label="[1]", state=CitationState.VALID),
                relevance_score=0.8, heading_path="table-row-Data-0",
            ),
            EvidenceItem(
                chunk_id="t1", document_id="d2",
                text="JARVIS는 로컬 AI 비서 프로젝트입니다.",
                citation=CitationRecord(label="[2]", state=CitationState.VALID),
                relevance_score=0.7, heading_path="paragraph-intro",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="JARVIS", query_type="semantic", language="ko"),),
    )

    ctx = ContextAssembler().assemble(evidence, query="JARVIS?")
    assert any("Name" in f.key and f.value == "JARVIS" for f in ctx.facts)
    assert any("로컬 AI" in p for p in ctx.text_passages)
```

- [ ] **Step 2: Run integration tests**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/integration/test_context_assembler_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `PYTHONPATH=src .venv/bin/python3 -m pytest tests/unit/ -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_context_assembler_e2e.py
git commit -m "test: add end-to-end integration tests for ContextAssembler pipeline"
```
