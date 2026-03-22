# JARVIS — Next Tasks (updated 2026-03-23)

## 완료 — 총 27개 항목

### Phase 0~1 (검색/인덱싱/LLM) — 10개
- [x] FTS + Vector 검색 병렬화, LLM 스트리밍, 출처 표시, MLX 전환
- [x] QueryDecomposer, Vector Search, Reranker, Semantic Chunking
- [x] 시스템 프롬프트 중앙화, EXAONE 4.0 벤치마크

### Priority 1 (안정성/품질) — 5개
- [x] PDF 구조화 청킹 (87%↓), Claim-level 인용 검증
- [x] 질문 복잡도 모델 라우팅, MLX 테스트 수정, KB 재인덱싱

### Priority 2 (기능 확장) — 5개
- [x] HWPX 테이블, tree-sitter AST, Citation post-verification
- [x] Silero VAD, SwiftUI 스트리밍 렌더링

### Phase 2 — 7개
- [x] Tier 3 메모리, MCP Transport, JARVIS 음성 페르소나
- [x] Wake Word (Python CLI + Swift 메뉴바 통합)
- [x] TTS 한국어 지원 (Jian Premium) + 마크업 제거
- [x] 커스텀 wake word 학습 인프라 (수집 + 학습 스크립트)
- [x] Qwen3-TTS fine-tuning 인프라 (음성 수집 + 임베딩 추출)

## Remaining — 데이터 수집 후 실행

- [ ] "헤이 자비스" 음성 샘플 50개 수집 → `scripts/collect_wake_word_samples.py`
- [ ] 커스텀 wake word 모델 학습 → `scripts/train_wake_word.py`
- [ ] JARVIS 참조 음성 20개 수집 → `scripts/collect_voice_samples.py`
- [ ] Qwen3-TTS 음성 클로닝 → `scripts/finetune_tts.py`

## 현재 브랜치

- Branch: `feature/menubar-ui-refresh`
- 40+ commits ahead of origin
- 테스트: 490 passed
- Swift: Build complete
