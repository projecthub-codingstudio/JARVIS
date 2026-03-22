# JARVIS — Next Tasks (updated 2026-03-23)

이전 세션에서 완료된 작업과 남은 작업 우선순위.

## 완료 (2026-03-22~23 세션)

- [x] FTS + Vector 검색 병렬화
- [x] LLM 스트리밍 응답 (REPL, 음성, 메뉴바)
- [x] 출처 표시 디자인 개선
- [x] MLX 엔진 + EXAONE-3.5-7.8B 전환 (15x 속도 향상)
- [x] QueryDecomposer 개선 (파일명 추출, 불용어 제거)
- [x] Vector Search 활성화 (BGE-M3 임베딩 22,692개)
- [x] Cross-encoder Reranker (다국어 mmarco)
- [x] Semantic Chunking (Table/Code/Paragraph 전략)
- [x] 시스템 프롬프트 중앙화 + key=value 데이터 지시
- [x] EXAONE 4.0 벤치마크 + deep tier 등록
- [x] PDF 구조화 청킹 — 19,543→2,620 청크 (87% 감소)
- [x] Claim-level 인용 검증 — 주장 단위 분리 + 숫자값 매칭
- [x] 질문 복잡도 기반 모델 라우팅 — simple→balanced, complex→deep
- [x] test_skips_mlx_when_probe_fails 수정
- [x] Knowledge base 재인덱싱 — 22,692→5,855 청크
- [x] HWPX 구조화 파싱 — XML 테이블 추출
- [x] tree-sitter 코드 청킹 — AST 기반 Python/JS/TS
- [x] Citation post-verification — 스트리밍 시 답변 먼저 표시
- [x] Silero VAD — ML 기반 음성 감지
- [x] SwiftUI 스트리밍 렌더링 — 서버 모드 브리지 + 실시간 토큰
- [x] Tier 3 메모리 — LLM 기반 사용자 지식 추출/프롬프트 주입
- [x] MCP Transport — stdio 서버, 3개 도구 노출

## Priority 1~3 Phase 2

(대부분 완료)

## Remaining — Future Work

- [ ] Wake word (push-to-talk → wake word 전환, OpenWakeWord 통합)
- [ ] Avatar voice/persona 레이어 (Qwen3-TTS 페르소나)
- [ ] Apple SFSpeechRecognizer / Siri Shortcuts 평가
- [ ] MCP persistent server mode (현재 per-session, 향후 daemon 모드)
- [ ] Tier 3 메모리 LLM 기반 추출 (현재 패턴 기반, 향후 LLM 분석 추가)

## 현재 브랜치

- Branch: `feature/menubar-ui-refresh`
- 30+ commits ahead of origin
- PR 미생성
