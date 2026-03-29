# 2026-03-26 Intent JSON Contract

## 목적

`Planner`의 heuristic intent를 주 경로로 두지 않고,
LLM이 구조화된 intent JSON을 생성할 수 있도록 backend 계약을 먼저 고정한다.

heuristic은 fallback으로만 남는다.

## QueryAnalysis 확장 계약

backend는 아래 형태의 JSON을 생성할 수 있어야 한다.

```json
{
  "intent": "diet_plan_lookup",
  "sub_intents": ["smalltalk"],
  "entities": {
    "day_numbers": [9],
    "meal_slots": ["dinner"]
  },
  "search_terms": ["다이어트", "식단표", "9일차", "저녁"],
  "target_file": "",
  "language": "ko",
  "confidence": 0.94,
  "source": "llm_json"
}
```

## 필드 의미

- `intent`
  - 주 실행 intent
- `sub_intents`
  - 인사말 등 보조 의도
- `entities`
  - retrieval/action에 필요한 구조화 슬롯
- `search_terms`
  - retrieval query expansion용 키워드
- `target_file`
  - 특정 파일 지시가 있을 때만 사용
- `language`
  - `ko`, `en`, `mixed`
- `confidence`
  - `0.0 ~ 1.0`
- `source`
  - `llm_json`, `heuristic`, `lightweight`

## 적용 원칙

- backend는 우선 LLM JSON을 파싱한다.
- JSON이 유효하면 그 결과가 planner의 주 결과다.
- JSON이 실패하면 heuristic `QueryAnalysis`를 fallback으로 사용한다.
- Swift/frontend는 planner source가 heuristic인지 LLM인지 직접 판단하지 않는다.

## 현재 구현 상태

- `QueryAnalysis`가 `sub_intents`, `entities`를 수용
- `QueryAnalysis.from_payload(...)`로 LLM JSON 복원 가능
- `LLMIntentJSONBackend`가 `LLMBackendProtocol.generate(...)`를 사용해 intent JSON을 복원 가능
- runtime context는 이미 로드된 LLM backend가 있으면 planner lightweight backend로 재사용
- backend가 없거나 실패하면 heuristic이 fallback

## 다음 단계

1. local/service backend에 LLM intent JSON 생성기 추가
2. `Planner` lightweight backend가 JSON을 `QueryAnalysis.from_payload(...)`로 복원
3. `intent_policy`는 fallback 전용으로 축소
4. `answer_text`, `speech_text`도 같은 structured backend 응답 안에서 생성
