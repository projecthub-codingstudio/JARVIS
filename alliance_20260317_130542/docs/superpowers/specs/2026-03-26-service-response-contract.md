# 2026-03-26 Service Response Contract

## 목적

메뉴바 앱과 이후의 다른 프론트엔드가 backend 응답을 임의로 해석하지 않도록,
JARVIS service가 반환하는 화면/가이드용 payload를 명시적으로 고정한다.

## ask_text 응답 계약

`ask_text` 성공 응답은 아래 세 payload를 함께 포함한다.

```json
{
  "response": { "...": "기존 MenuResponse 전체" },
  "answer": {
    "text": "사용자에게 보여줄 최종 응답",
    "has_evidence": true,
    "citation_count": 2,
    "full_response_path": "/tmp/response.md"
  },
  "guide": {
    "loop_stage": "waiting_user_reply",
    "clarification_prompt": "출발 위치를 알려주세요.",
    "suggested_replies": ["현재 위치", "집"],
    "clarification_options": ["현재 위치", "집"],
    "missing_slots": ["origin"],
    "clarification_reasons": ["origin"],
    "intent": "route_guidance",
    "skill": "route",
    "should_hold": true,
    "has_clarification": true,
    "interaction_mode": "route",
    "exploration_mode": "document",
    "target_file": "guide.md",
    "target_document": "guide"
  }
}
```

## 설계 원칙

- `response`는 기존 Swift UI 호환성을 위한 전체 payload다.
- `answer`는 프론트엔드가 결과 텍스트와 근거 여부를 빠르게 소비하기 위한 축약 계약이다.
- `guide`는 Guide 창 상태 결정을 backend가 더 직접 소유하기 위한 명시적 계약이다.
- `guide`가 존재하면 프론트엔드는 임의의 질문 추론보다 backend `guide`를 우선 적용한다.
- clarification 필요 여부의 최소 추론도 backend가 수행하고, 프론트엔드는 예외 경로에서만 legacy directive를 본다.
- 새 프론트엔드는 가능하면 `guide`와 `answer`를 우선 사용하고, `response`는 호환 계층으로만 본다.

## runtime_state 응답 계약

`runtime_state`는 frontend 상태 표시를 위한 단일 조회 계약이다.

```json
{
  "health": { "...": "기존 HealthResponse" },
  "service": {
    "contract_version": "2026-03-26",
    "frontend_mode": "multi-client",
    "runtime_owner": "backend-service"
  }
}
```

## 다음 단계

- Swift Guide 렌더링이 `guide` payload를 우선 사용하도록 이전
- web frontend가 같은 `answer` / `guide` / `runtime_state` 계약을 그대로 사용
