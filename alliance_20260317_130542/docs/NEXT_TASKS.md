# JARVIS — Next Tasks (updated 2026-03-23)

## 완료 (2026-03-22~23 세션) — 총 24+ 항목

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
- [x] Claim-level 인용 검증
- [x] 질문 복잡도 기반 모델 라우팅
- [x] test_skips_mlx_when_probe_fails 수정
- [x] Knowledge base 재인덱싱 — 22,692→5,855 청크

### Priority 2 (기능 확장)
- [x] HWPX 구조화 파싱 — XML 테이블 추출
- [x] tree-sitter 코드 청킹 — AST 기반
- [x] Citation post-verification
- [x] Silero VAD — ML 기반 음성 감지
- [x] SwiftUI 스트리밍 렌더링

### Phase 2
- [x] Tier 3 메모리 — 사용자 지식 추출/주입
- [x] MCP Transport — stdio 서버
- [x] JARVIS 음성 페르소나 — Iron Man 스타일
- [x] Wake Word — "Hey JARVIS" (Python CLI 프로토타입)
- [x] TTS 한국어 지원 — Jian Premium (ko_KR)
- [x] TTS 마크업 제거 — 자연스러운 음성 출력

## Remaining — Next Priorities

### Wake Word / 음성 품질 개선 (Swift 통합 필요)
- [ ] **Swift 메뉴바에 wake word 통합** — NativeAudioRecorder의 AVAudioEngine 활용
  - Python pyaudio 한계: 앞부분 잘림, 낮은 인식률, 48kHz 리샘플링 품질
  - Swift AVAudioEngine: warm mic, 상시 버퍼, 네이티브 포맷 → 품질 우수
  - OpenWakeWord ONNX를 Swift/CoreML로 변환하거나 Python 서브프로세스로 브리지
- [ ] **Wake word 커스텀 학습** — "헤이 자비스" 한국어 발음으로 학습
  - OpenWakeWord training pipeline 또는 Mycroft Precise 활용
- [ ] **Qwen3-TTS fine-tuning** — JARVIS 참조 음성으로 커스텀 보이스

### 기타
- [ ] Apple SFSpeechRecognizer / Siri Shortcuts 평가
- [ ] MCP persistent daemon mode
- [ ] Tier 3 메모리 LLM 기반 추출 강화

## 현재 브랜치

- Branch: `feature/menubar-ui-refresh`
- 38+ commits ahead of origin
- 테스트: 490 passed
- PR 미생성
