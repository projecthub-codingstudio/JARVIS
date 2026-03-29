# 2026-03-26 Frontend / Backend RPC Architecture

## 목적

JARVIS를 `Swift 전용 메뉴바 앱 + Python 브리지` 구조에서
`다중 프론트엔드 + 공용 백엔드 서비스` 구조로 전환하기 위한 기준 아키텍처를 정의한다.

이 문서는 설명용이 아니라 이후 구현의 기준선이다.

## 현재 구조의 문제

1. Swift 메뉴바 앱이 Python 프로세스 생명주기를 직접 관리한다.
2. one-shot / persistent 경로가 혼합되어 장애 모델이 분산되어 있다.
3. UI 계층이 백엔드 장애 복구와 stderr/stdout 처리까지 떠안는다.
4. Web frontend 추가 시 현재 구조를 재사용할 수 없다.

## 목표 구조

```text
[Frontend Clients]
  - Swift MenuBar
  - Web UI
  - Future Mobile

          RPC

[Jarvis Application Service]
  - Session state
  - Guide state
  - Retrieval / reasoning
  - Approval workflow
  - Health / metrics
  - TTS job creation

[Runtime Services]
  - Knowledge base
  - DB / vector index
  - STT
  - TTS
  - LLM runtime
```

## 현재 구현 상태

2026-03-26 현재 코드 기준 상태는 아래와 같다.

```text
[Swift MenuBar]
  -> JarvisServiceClient
     -> default: UDS
     -> fallback: stdio
     -> runtimeState / ask_text / transcribe_file / navigation_window
  -> JarvisGuideState
     -> latestAskResponse.answer / guide 우선 사용
     -> latestResponse는 내부 호환 원본으로만 유지

[Python Service]
  -> jarvis.service.application
  -> stdio_server / socket_server
  -> runtime_state / ask_text / normalize_query / navigation_window
  -> transcribe_file / synthesize_speech / export_draft / health
```

즉 메뉴바 앱의 기본 경로는 더 이상 `JarvisBridge.swift` 실행 코드에 의존하지 않는다.
`JarvisBridge.swift`는 legacy 호환 파일로 남아 있지만 메뉴바 타깃 기본 경로의 중심은 아니다.

## 역할 분리

### Frontend

- 사용자 입력 수집
- 화면 렌더링
- 로컬 녹음 / 재생 제어
- RPC 요청 / 응답 처리

### Backend

- 세션 문맥 유지
- 질의 해석
- guide directive 생성
- citation / status 조립
- 로직 처리
- tool orchestration
- approval 정책

## Guide 창의 위치

Guide 창 자체는 frontend UI다.

하지만 Guide가 어떤 모드인지, 어떤 후속 질문을 해야 하는지,
어떤 suggested replies를 노출해야 하는지는 backend가 결정한다.

```text
Guide UI = Frontend
Guide state logic = Backend
```

## RPC 계약 원칙

1. 모든 요청은 `request_id`를 가진다.
2. 모든 응답은 `ok` 또는 `error` 중 하나를 가진다.
3. stdout이 비어도 안 된다.
4. backend는 실패 시에도 구조화된 에러를 반환해야 한다.
5. frontend는 backend 내부 stderr 형식에 의존하지 않는다.

## 최소 RPC 메시지

요청:

```json
{
  "request_id": "req_123",
  "session_id": "sess_abc",
  "request_type": "ask_text",
  "payload": {
    "text": "안녕하세요"
  }
}
```

응답:

```json
{
  "request_id": "req_123",
  "session_id": "sess_abc",
  "ok": true,
  "payload": {
    "answer": {
      "text": "안녕하세요. 무엇을 도와드릴까요?"
    },
    "guide": {
      "mode": "presenting",
      "skill": "conversation_support",
      "prompt": "",
      "suggested_replies": ["오늘 일정", "문서 찾아줘"]
    },
    "citations": [],
    "status": {
      "safe_mode": false,
      "degraded_mode": false
    }
  }
}
```

에러:

```json
{
  "request_id": "req_123",
  "session_id": "sess_abc",
  "ok": false,
  "error": {
    "code": "BACKEND_UNAVAILABLE",
    "message": "Jarvis service is not ready",
    "retryable": true
  }
}
```

## 마이그레이션 단계

1. 공용 RPC 프로토콜과 application service 추가
2. 기존 `menu_bridge.py` 기능을 application service 뒤로 이동
3. Swift는 subprocess가 아니라 RPC client만 사용
4. Web frontend는 동일 RPC를 사용
5. persistent / one-shot 혼합 구조 제거

## 초기 구현 원칙

- transport는 우선 stdio로 시작할 수 있다.
- 단, transport와 application service를 분리한다.
- 이후 Unix domain socket / HTTP / WebSocket으로 교체 가능해야 한다.

## 파일 배치

```text
src/jarvis/service/protocol.py
src/jarvis/service/application.py
src/jarvis/service/stdio_server.py
src/jarvis/service/socket_server.py
src/jarvis/service/socket_path.py
tests/unit/test_service_protocol.py
macos/JarvisMenuBar/Sources/JarvisServiceClient.swift
macos/JarvisMenuBar/Sources/JarvisServiceManager.swift
macos/JarvisMenuBar/Sources/JarvisRuntimeSupport.swift
macos/JarvisMenuBar/Sources/JarvisSocketTransport.swift
```

## 비목표

- 이번 단계에서 Swift 전체를 새 RPC client로 교체하지 않는다.
- Web frontend를 즉시 구현하지 않는다.
- transport 최종 선택을 지금 확정하지 않는다.

위 세 항목 중 첫 번째는 현재 구현이 이미 상당 부분 넘어섰다.
남은 비목표는 Web frontend 즉시 구현과 transport의 최종 운영 방식 확정이다.
