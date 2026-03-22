# JARVIS — Next Tasks (updated 2026-03-23)

## 완료 (2026-03-22~23 세션) — 총 24개 항목

### Phase 0~1 (검색/인덱싱/LLM)
- [x] FTS + Vector 검색 병렬화
- [x] LLM 스트리밍 응답 (REPL, 음성, 메뉴바)
- [x] 출처 표시 디자인 개선
- [x] MLX 엔진 + EXAONE-3.5-7.8B 전환 (15x 속도 향상)
- [x] QueryDecomposer 개선 (파일명 추출, 불용어 제거)
- [x] Vector Search 활성화 (BGE-M3 임베딩)
- [x] Cross-encoder Reranker (다국어 mmarco)
- [x] Semantic Chunking (Table/Code/Paragraph 전략)
- [x] 시스템 프롬프트 중앙화 + key=value 데이터 지시
- [x] EXAONE 4.0 벤치마크 + deep tier 등록

### Priority 1 (안정성/품질)
- [x] PDF 구조화 청킹 — 19,543→2,620 청크 (87%↓)
- [x] Claim-level 인용 검증 — 주장 단위 분리 + 숫자값 매칭
- [x] 질문 복잡도 기반 모델 라우팅 — simple→balanced, complex→deep
- [x] test_skips_mlx_when_probe_fails 수정
- [x] Knowledge base 재인덱싱 — 22,692→5,855 청크

### Priority 2 (기능 확장)
- [x] HWPX 구조화 파싱 — XML 테이블 추출
- [x] tree-sitter 코드 청킹 — AST 기반 Python/JS/TS
- [x] Citation post-verification — 스트리밍 시 답변 먼저 표시
- [x] Silero VAD — ML 기반 음성 감지
- [x] SwiftUI 스트리밍 렌더링 — 서버 모드 브리지 + 실시간 토큰

### Priority 3 / Phase 2
- [x] Tier 3 메모리 — 사용자 지식 추출/프롬프트 주입
- [x] MCP Transport — stdio 서버, 3개 도구 노출
- [x] JARVIS 음성 페르소나 — Iron Man AI 버틀러 (Daniel en_GB + Qwen3-TTS)
- [x] Wake Word — "Hey JARVIS" (OpenWakeWord hey_jarvis_v0.1)

## Remaining — Future Enhancements

- [ ] Qwen3-TTS fine-tuning (JARVIS 참조 음성으로 커스텀 보이스 학습)
- [ ] Apple SFSpeechRecognizer / Siri Shortcuts 평가
- [ ] MCP persistent daemon mode (현재 per-session)
- [ ] Tier 3 메모리 LLM 기반 추출 (현재 패턴 기반)
- [ ] Wake word → voice session 자동 연결 (현재 독립 모듈)
- [ ] pyaudio 대체 (sounddevice 또는 AVAudioEngine Python 브리지)

## 현재 브랜치

- Branch: `feature/menubar-ui-refresh`
- 33+ commits ahead of origin
- 테스트: 490 passed
- PR 미생성
