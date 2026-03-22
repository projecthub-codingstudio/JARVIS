# JARVIS — Next Tasks (updated 2026-03-23)

이전 세션에서 완료된 작업과 남은 작업 우선순위.

## 완료 (2026-03-22~23 세션)

- [x] FTS + Vector 검색 병렬화
- [x] LLM 스트리밍 응답 (REPL, 음성, 메뉴바)
- [x] 출처 표시 디자인 개선
- [x] MLX 엔진 + EXAONE-3.5-7.8B 전환 (Ollama+Qwen3-14B 대비 15x 속도 향상)
- [x] QueryDecomposer 개선 (파일명 추출, 불용어 제거)
- [x] Vector Search 활성화 (BGE-M3 임베딩 22,692개)
- [x] Cross-encoder Reranker (다국어 mmarco)
- [x] Semantic Chunking (Table/Code/Paragraph 전략)
- [x] 시스템 프롬프트 중앙화 + key=value 데이터 지시
- [x] EXAONE 4.0 벤치마크 + deep tier 등록

## Priority 1 — 안정성/품질

- [ ] **PDF 청킹 품질 개선**
  - 씨샵.pdf: 19,543 청크 (avg 85자) — 너무 작음
  - LayoutChunkStrategy 구현: 최소 청크 크기 하한(200자) + 페이지/섹션 경계 존중
  - PyMuPDF 블록 좌표 활용

- [ ] **Claim-level 인용 검증**
  - 현재: 문장 단위 `[digit]` 태그 확인
  - 목표: 주장 단위 검증 (각 factual claim이 증거에 근거하는지)
  - 출처: AUDIT_REPORT Section 12

- [ ] **test_skips_mlx_when_probe_fails 수정**
  - MLX probe 테스트 1건 계속 실패
  - probe 캐시 TTL 로직 검토 필요

- [ ] **질문 복잡도 기반 모델 선택**
  - 간단한 데이터 조회 → EXAONE-3.5-7.8B (1.5초)
  - 복잡한 분석/추론 → EXAONE-4.0-32B (8.8초)
  - Planner의 intent 분류 활용

## Priority 2 — 기능 확장

- [ ] **Silero VAD 업그레이드**
  - 에너지 기반 → ML 기반 음성 감지
  - 출처: NEXT_ITERATION_UI_VOICE.md Priority 1

- [ ] **메뉴바 SwiftUI 스트리밍 렌더링**
  - Python bridge에서 `stream_chunk` JSON은 이미 전송
  - SwiftUI 측에서 수신하여 실시간 텍스트 표시 구현 필요

- [ ] **Citation post-verification**
  - 답변 먼저 표시, 인용 비동기 검증
  - 출처: NEXT_ITERATION Priority 2

- [ ] **tree-sitter 코드 청킹**
  - 현재 regex 기반 def/class 감지 → AST 기반 정확한 함수 경계
  - CodeChunkStrategy에 tree-sitter 통합

- [ ] **HWP/HWPX 구조화 파싱**
  - 현재 텍스트만 추출 → 표/목록 분리하여 TableElement로 변환
  - DocumentChunkStrategy 구현

## Priority 3 — Phase 2

- [ ] Wake word (push-to-talk → wake word 전환)
- [ ] LLM-extracted 사용자 지식 (Tier 3 메모리)
- [ ] MCP transport (MCP-shaped → 실제 MCP 프로토콜)
- [ ] Avatar voice/persona 레이어
- [ ] Apple SFSpeechRecognizer / Siri Shortcuts 평가

## 현재 브랜치

- Branch: `feature/menubar-ui-refresh`
- 20+ commits ahead of origin
- PR 미생성
