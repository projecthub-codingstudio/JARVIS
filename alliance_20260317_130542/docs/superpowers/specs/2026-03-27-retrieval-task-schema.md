# Retrieval Task Schema

Date: 2026-03-27

Related documents:

- [2026-03-27-retrieval-final-consensus.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-final-consensus.md)
- [2026-03-27-retrieval-execution-plan.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/plans/2026-03-27-retrieval-execution-plan.md)

## Purpose

Define the planner output contract that downstream retrieval must consume.

This schema exists to stop query intent from being reinterpreted in multiple lower layers.

## Top-Level Shape

```json
{
  "retrieval_task": "document_qa",
  "confidence": 0.92,
  "entities": {
    "document": "한글문서 파일형식",
    "topic": "그리기 개체 자료 구조",
    "subtopic": "기본 구조"
  },
  "search_terms": [
    "한글문서 파일형식",
    "그리기 개체 자료 구조",
    "기본 구조"
  ],
  "sub_intents": ["smalltalk"],
  "language": "ko",
  "source": "planner"
}
```

## Required Fields

### `retrieval_task`

Type:

- string

Allowed values in v1:

- `document_qa`
- `table_lookup`
- `code_lookup`
- `multi_doc_qa`
- `live_data_request`
- `smalltalk`

### `confidence`

Type:

- float in `[0.0, 1.0]`

Meaning:

- confidence of the routing decision
- used to determine whether to accept heuristic routing or escalate to the LLM router

### `entities`

Type:

- object

Meaning:

- structured extraction of retrieval-relevant entities

### `search_terms`

Type:

- string array

Meaning:

- normalized retrieval-oriented terms for downstream search

## Optional Fields

### `sub_intents`

Type:

- string array

Examples:

- greeting attached to task query
- clarification request attached to lookup query

### `language`

Type:

- `ko`, `en`, `mixed`

### `source`

Type:

- string

Examples:

- `heuristic`
- `llm_router`
- `planner`

## Entity Schema by Task

### 1. `document_qa`

```json
{
  "document": "한글문서 파일형식",
  "topic": "그리기 개체 자료 구조",
  "subtopic": "기본 구조",
  "section_hint": "그리기 개체 자료 구조"
}
```

### 2. `table_lookup`

```json
{
  "table": "14day_diet_supplements_final",
  "row_ids": ["11", "12"],
  "fields": ["Breakfast", "Dinner"]
}
```

### 3. `code_lookup`

```json
{
  "target_file": "pipeline.py",
  "symbol": "Pipeline",
  "symbol_type": "class"
}
```

### 4. `multi_doc_qa`

```json
{
  "topics": ["임베딩", "검색"],
  "document_hints": ["architecture.md", "planner.py"]
}
```

### 5. `live_data_request`

```json
{
  "capability": "weather",
  "location": "Seoul"
}
```

## Routing Rules

### Heuristic router accepts immediately when:

- `confidence >= 0.8`

### LLM router is invoked when:

- `confidence < 0.8`
- multiple tasks compete
- entities are incomplete for the selected task

## Downstream Expectations

### `DocumentStrategy` consumes

- `retrieval_task == "document_qa"`
- `entities.document`
- `entities.topic`
- `entities.subtopic`
- `search_terms`

### `TableStrategy` consumes

- `retrieval_task == "table_lookup"`
- `entities.row_ids`
- `entities.fields`
- `search_terms`

### `CodeStrategy` consumes

- `retrieval_task == "code_lookup"`
- `entities.target_file`
- `entities.symbol`
- `search_terms`

## Explicit Non-Goals

This schema does not:

- encode answer formatting
- encode TTS behavior
- encode citation formatting
- decide retrieval scores directly

It only defines retrieval routing and retrieval intent.
