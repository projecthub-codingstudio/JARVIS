# 2026-03-26 Service Migration Plan

## 목표

Swift 메뉴바 앱이 Python subprocess 생명주기를 직접 관리하지 않고,
공용 JARVIS backend service를 RPC로 호출하도록 단계적으로 전환한다.

## 현재 완료 상태

- [x] 공용 RPC 프로토콜 추가
- [x] Python application service 파사드 추가
- [x] stdio transport 추가
- [x] Swift service client 추가
- [x] 메뉴바 앱 기본 의존성을 `JarvisServiceClient()`로 전환
- [x] `ask_text` 서비스 경로 연결
- [x] `normalize_query` 서비스 경로 연결
- [x] `navigation_window` 서비스 경로 연결
- [x] `transcribe_file` 서비스 경로 연결
- [x] `health` 서비스 경로 연결
- [x] `synthesize_speech` 서비스 경로 연결
- [x] `export_draft` 서비스 경로 연결
- [x] Unix domain socket transport 골격 추가
- [x] Swift UDS transport 골격 추가
- [x] UDS service manager 추가
- [x] 기본 transport를 `uds` 우선으로 전환
- [x] `uds -> stdio` fallback 추가
- [x] 공통 runtime 설정/오류 타입을 `JarvisBridge`에서 분리
- [x] frontend 상태 조회를 `runtimeState()` 단일 API로 집약 시작
- [x] frontend protocol에서 분산 startup polling 메서드 제거
- [x] `JarvisBridge.swift`를 메뉴바 빌드 타깃에서 격리
- [x] backend `runtime_state` 계약 추가
- [x] backend `ask_text`에 `answer` / `guide` 명시 계약 추가
- [x] Swift Guide가 backend `guide` payload를 우선 사용하도록 이전 시작
- [x] Swift Guide/PendingContext가 `guideDirective` 대신 `backend guide` 중심으로 전환
- [x] Swift UI가 `latestAskResponse.answer/guide`를 우선 보관하도록 전환 시작
- [x] 복사/내보내기/출처 표시용 데이터 접근을 `JarvisGuideState`로 집약 시작

## 현재 파일 기준

```text
src/jarvis/service/protocol.py
src/jarvis/service/application.py
src/jarvis/service/stdio_server.py
src/jarvis/service/socket_path.py
src/jarvis/service/socket_server.py
macos/JarvisMenuBar/Sources/JarvisServiceClient.swift
macos/JarvisMenuBar/Sources/JarvisServiceManager.swift
macos/JarvisMenuBar/Sources/JarvisRuntimeSupport.swift
macos/JarvisMenuBar/Sources/JarvisSocketTransport.swift
```

## 다음 단계

### Phase 1. Runtime 안정화

- [ ] service stderr / stdout 진단을 frontend 독립 계약으로 정리
- [~] health / startup 상태를 service 응답으로 통합
- [~] knowledge base 경로 전달 규약 고정

### Phase 2. Transport 전환

- [x] Swift client가 stdio / uds 중 하나를 환경설정으로 선택
- [x] Python `socket_server`를 장기 실행 서비스로 실제 운영 경로에 연결
- [~] subprocess 1회 실행 경로를 점진 축소

### Phase 3. Frontend 독립화

- [~] Guide 상태를 backend 단일 진실원으로 완전 이전
- [~] 메뉴바 앱에서 legacy `JarvisBridge` 직접 의존 제거
- [ ] web frontend용 동일 계약 재사용

### Phase 4. Heuristic 축소

- [x] 현재 heuristic 개입 지점 문서화
- [ ] `intent_policy`를 fallback 계층으로 축소
- [ ] `stub speech shaping` 규칙 축소
- [ ] menu bar `ask_text`의 model-backed 복귀 경로 재도입
- [ ] `intent_json`, `answer_text`, `speech_text`를 backend 주 응답 계약으로 고정

## 다음 실행 우선순위

1. [2026-03-26-heuristic-review.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-26-heuristic-review.md) 기준으로 heuristic 유지/축소 범위 고정
2. `intent_policy`와 `stub speech shaping` 책임 축소
3. menu bar `ask_text`의 model-backed 복귀 경로 설계 및 검증
4. [2026-03-26-runtime-validation-checklist.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/plans/2026-03-26-runtime-validation-checklist.md) 기준으로 메뉴바 런타임 검증
5. UDS 장기 실행 서비스 운영 책임을 `launchd` 또는 별도 manager로 고정할지 결정

## 이번 구현 범위

1. UDS 장기 실행 서비스 매니저 추가
2. 기본 transport를 `uds` 우선으로 전환하고 `stdio` fallback 유지
3. 공통 runtime 설정/오류 타입을 별도 파일로 분리
4. frontend 상태 조회를 서비스 클라이언트 단일 API로 집약
5. `JarvisBridge.swift`를 빌드 타깃에서 제거해 legacy 실행 코드 격리
6. backend `runtime_state` 계약으로 frontend 상태 조회 기반 이동
7. backend `ask_text` guide 계약 명시화
8. Swift Guide가 backend `guide` payload를 우선 사용하도록 이전
9. Python 테스트와 Swift build 검증

## 완료 기준

- 주요 메뉴바 기능이 `JarvisServiceClient` 경유로 동작 가능
- stdio와 uds 양쪽 transport를 수용할 수 있는 구조 확보
- `JarvisServiceClient`가 `JarvisBridge` 공통 타입에 구조적으로 덜 묶인 상태 확보
- 이후 web frontend가 동일 backend contract를 재사용 가능
