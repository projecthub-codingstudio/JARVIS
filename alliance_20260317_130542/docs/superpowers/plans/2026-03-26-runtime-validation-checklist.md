# 2026-03-26 Runtime Validation Checklist

## 목적

서비스 계층 분리가 코드상으로 끝난 이후,
실제 메뉴바 런타임이 새 구조를 따라 동작하는지 검증하기 위한 체크리스트다.

## 1. 서비스 기동 경로

- [ ] 메뉴바 앱 시작 후 `JarvisServiceManager`가 UDS 서비스를 기동한다.
- [x] 기본 transport가 `uds`일 때 요청 전 서비스 readiness를 보장한다.
- [ ] UDS 실패 시 `stdio` fallback 로그가 남는다.
- [x] fallback 이후 ask / transcribe / health가 실제 응답을 반환한다.

## 2. 질의 응답 경로

- [x] 텍스트 `안녕하세요` 입력 시 `ask_text`가 `ServiceAskResponse`로 반환된다.
- [ ] Guide 창이 `answer.text`를 최종 응답으로 표시한다.
- [x] Guide loop stage가 `payload.guide.loop_stage` 기준으로 보인다.
- [x] clarification prompt가 필요할 때 frontend 추론이 아니라 backend `guide`가 반영된다.

## 3. 음성 경로

- [ ] 녹음 후 `transcribe_file` RPC 호출이 정상 완료된다.
- [ ] 음성 인식 결과가 `ask_text`로 이어진다.
- [x] 응답 TTS가 `synthesize_speech` RPC를 통해 생성된다.
- [ ] 응답 TTS가 frontend에서 실제 재생된다.

## 4. 탐색/가이드 경로

- [ ] navigation window가 `navigation_window` RPC로 갱신된다.
- [ ] 문서/소스 탐색 후보가 Guide 창에 표시된다.
- [ ] 후보 선택 후 후속 질의가 현재 선택 컨텍스트를 반영한다.

## 5. 지식기반 및 상태 경로

- [x] `runtime_state`가 health와 startup 상태를 정상 반환한다.
- [ ] knowledge base 경로 변경 후 서비스 재기동이 반영된다.
- [ ] Guide/설정 화면이 `runtime_state` 기반 상태를 표시한다.

## 6. 남은 위험

- [ ] UDS 장기 실행 서버의 운영 책임을 `launchd` 등 외부 매니저로 넘길지 결정
- [ ] `JarvisBridge.swift` legacy 파일 완전 제거 여부 결정
- [ ] stdout/stderr 진단 계약을 frontend 비의존 구조로 더 고정

## 이번 검증 결과 메모

- UDS 실서비스 왕복 확인:
  - `runtime_state`: `ok=true`, `runtime_owner=backend-service`
  - `ask_text('안녕하세요')`: `ok=true`, `payload_keys=['answer','guide','response']`
  - `synthesize_speech`: `ok=true`, AIFF 경로 반환
- stdio one-shot 검증:
  - `runtime_state`: `returncode=0`, JSON 정상 반환
- 현재 자동 검증만으로 확인된 health 상태:
  - lightweight `runtime_state`는 `healthy=false`
  - 원인: `knowledge_base` 미설정 / lightweight mode 경고
- 남은 항목은 메뉴바 UI 직접 실행으로 확인해야 한다.
