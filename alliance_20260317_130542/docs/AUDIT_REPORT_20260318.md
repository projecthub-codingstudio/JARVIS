# JARVIS 구현 상태 검수 보고서

**검수일**: 2026-03-19
**기술문서**: TASK-E93DF600.md (아키텍처 분석), TASK-9A8DC5D5.md (구현 명세)
**구현 경로**: alliance_20260317_130542/

---

## 전체 요약

이 보고서는 `TASK-E93DF600.md`, `TASK-9A8DC5D5.md`, 그리고 구현 이후 추가된
`docs/superpowers/specs/`, `docs/superpowers/plans/` 문서를 기준으로 다시 대조했다.

현재 기준선은 `JARVIS 0.1.0-beta1`이며, 본 보고서는 `Beta 1 기능 완료 + 후속 UI/voice 개선 분리` 상태를 반영한다.

- 아키텍처 핵심 요구(하이브리드 검색, 승인형 내보내기, Governor, 최신성, 메뉴바 브리지)는 대부분 구현됐다.
- 부분 구현으로 남는 축은 `ModelRouter의 Governor 결합 심화`, `정교한 claim-level 인용 검증`, `관측성 심화`, `운영 하드닝`이다.
- 명세와 구현의 차이는 주로 `타입/이름 계약`, `Reranker/MeCab-ko의 명시적 유보`, `90% coverage 기준 미도달`에 남아 있다.

---

## 1. 잘 구현된 핵심 영역

| 영역 | 상태 | 핵심 파일 |
|------|------|-----------|
| **Contracts 계층** | ✅ 완벽 | 프로토콜 12개, 모델 12개, 에러 19개 코드, 상태 6개 enum |
| **인덱싱 파이프라인** | ✅ 프로덕션급 | PDF/DOCX/PPTX/XLSX/HWPX/HWP/SQL + 100개 확장자 + 텍스트 자동감지 |
| **FTS5 + Kiwi 형태소** | ✅ | 한국어 형태소 확장 검색, 지연 큐 backfill |
| **Governor 시스템 감지** | ✅ | psutil + pmset 실제 센서, swap/thermal/battery 임계값 |
| **LLM 듀얼 백엔드** | ✅ | MLX primary + Ollama fallback + stub 3단 폴백 |
| **Freshness 체계** | ✅ | STALE 자동감지(SHA-256 해시 비교), freshness boost, tombstone, 한국어 경고 |
| **파일 워처** | ✅ | 생성/수정/삭제/이동/디렉토리이름변경 전부 처리, stale 자동 정리 |

---

## 2. 아키텍처 명세 (TASK-E93DF600) 검수

### Section 4: 시스템 요구사항

| Feature | Status | Implementation File | Notes |
|---|---|---|---|
| M1 Max 64GB 타겟 | ✅ | `app/config.py:32` | `memory_limit_gb = 16.0` (worst-case 기준) |
| 순차 모델 로딩 (동시 금지) | 🔧 | `runtime/model_router.py` | 단일 활성 모델과 메모리 버짓 체크 구현, Governor 연동은 단순화됨 |
| 15-20GB 메모리 버짓 | ✅ | `core/governor.py:115`, `app/config.py:32` | Governor 16GB 제한 |
| Swap/thermal/battery 정책 | ✅ | `core/governor.py:33-106` | psutil + pmset 실제 센서 |

### Section 5/6: 아키텍처 결정 매트릭스

| Feature | Status | Implementation File | Notes |
|---|---|---|---|
| CLI REPL | ✅ | `cli/repl.py` | 인용 표시, 경고 포함 |
| 메뉴바 UI | ✅ | `macos/JarvisMenuBar/` | SwiftUI 메뉴바 셸 + 장기 실행 Python 브리지 + 승인 패널 + live voice loop + health status 구현 |
| MLX primary 런타임 | ✅ | `runtime/mlx_backend.py` | mlx_lm.load/generate, Metal cache clear |
| llama.cpp (Ollama) fallback | ✅ | `runtime/llamacpp_backend.py` | REST API, think:false, keep_alive=0 |
| SQLite FTS5 | ✅ | `sql/schema.sql:50-70`, `retrieval/fts_index.py` | FTS5 + 트리거 + lexical_morphs |
| Vector DB (LanceDB) | ✅ | `retrieval/vector_index.py` | LanceDB 연결, add/remove/search 구현 |
| Hybrid search + RRF | ✅ | `retrieval/hybrid_search.py` | RRF k=60, FTS+vector 결합 |
| BGE-M3 / Qwen3-Embedding | ✅ | `runtime/embedding_runtime.py` | sentence-transformers 기반 on-demand 로드 |
| Kiwi 형태소 | ✅ | `retrieval/tokenizer_kiwi.py` | content-POS filter (NNG, NNP, VV 등) |
| MeCab-ko | ❌ | — | 명시적 유보 |
| 선택 폴더 인덱싱 | ✅ | `app/config.py:14`, `__main__.py:35` | knowledge_base/ 제한 |
| FSEvents 증분 인덱싱 | 🔧 | `indexing/file_watcher.py` | watchdog + polling fallback, 실시간 인덱싱 동작 |
| 승인 게이트 | ✅ | `cli/approval.py`, `tools/draft_export.py` | CLI 승인 + 실제 export 구현 |

### Section 7: 코어 아키텍처 계층

| Feature | Status | Implementation File | Notes |
|---|---|---|---|
| Interface: CLI REPL | ✅ | `cli/repl.py` | 출처 유형, staleness 경고, 한국어 메시지 |
| Interface: 승인 패널 | ✅ | `cli/approval.py` | CLI 승인 흐름 및 export 연동 |
| Interface: 메뉴바 브리지 | ✅ | `cli/menu_bridge.py`, `app/runtime_context.py` | JSON 응답/상태/출처 직렬화 |
| Orchestration: Governor | ✅ | `core/governor.py` | 실제 psutil+pmset, tier 다운그레이드 |
| Orchestration: Planner | ✅ | `core/planner.py` | Ollama 이중언어 키워드 추출, fallback |
| Orchestration: ToolRegistry | ✅ | `core/tool_registry.py` | 3-tool 허용목록 + handler dispatch |
| Orchestration: Orchestrator | ✅ | `core/orchestrator.py` | 7단계: governor→planner→검색→증거→생성→저장 |
| Knowledge: Parser | ✅ | `indexing/parsers.py` | 10+ 포맷, CP949/EUC-KR/UTF-16 BOM |
| Knowledge: Chunker | ✅ | `indexing/chunker.py` | heading-aware, 250-500 토큰, UTF-8 경계 |
| Knowledge: FTS5 | ✅ | `retrieval/fts_index.py` | 형태소 확장 검색 |
| Knowledge: Vector index | ✅ | `retrieval/vector_index.py` | LanceDB 기반 검색 구현 |
| Knowledge: 문서 레지스트리 | ✅ | `sql/schema.sql`, `indexing/index_pipeline.py` | documents+chunks 스키마 |
| Memory: 대화 저장소 | ✅ | `memory/conversation_store.py` | SQLite + in-memory fallback |
| Memory: 작업 로그 | ✅ | `memory/task_log.py` | task_logs 테이블 |
| Runtime: MLX/llama.cpp | ✅ | `runtime/mlx_backend.py`, `runtime/llamacpp_backend.py` | 양쪽 구현 완료 |
| Runtime: 임베딩 엔진 | ✅ | `runtime/embedding_runtime.py` | BGE-M3 임베딩 구현 |
| Runtime: Reranker | ❌ | — | 명시적 유보 |
| Observability: Metrics | ✅ | `observability/metrics.py` | 11개 메트릭, measure() |
| Observability: Health | ✅ | `observability/health.py` | 9개 체크 (core 4 + runtime 5: model/embedding/vector_db/watcher/governor) |
| Observability: Tracing | 🔧 | `observability/tracing.py` | 경량 in-memory tracer 구현, 외부 export/전면 연동은 미완 |
| Tools: ReadFile | ✅ | `tools/read_file.py` | 허용된 루트 내 텍스트 파일 읽기 구현 |
| Tools: DraftExport | ✅ | `tools/draft_export.py` | 승인 게이트 연동 후 실제 export 수행 |

### Section 8: 핵심 데이터 플로우 (10단계)

| Step | Feature | Status | Notes |
|---|---|---|---|
| 1 | 한국어 질의 입력 | ✅ | REPL stdin |
| 2 | 의도 분류 | ✅ | Planner.analyze() |
| 3 | FTS + vector 병렬 검색 | 🔧 | 두 경로 모두 구현, 현재 호출 순서는 순차이며 병렬 실행 최적화는 미반영 |
| 4 | Freshness 검증 | ✅ | 해시 비교 STALE + boost |
| 5 | 컨텍스트 조합 (증거 + 대화) | ✅ | 최근 3턴 슬라이딩 윈도우를 LLM 입력에 주입 |
| 6 | Governor 모델 tier 선택 | ✅ | 다운그레이드 로직 |
| 7 | LLM 답변 생성 | ✅ | 한국어 시스템 프롬프트 |
| 8 | 인용 검증 | 🔧 | 보수적 문장 수준 근거 정렬 경고 구현, 정교한 claim-level 검증은 미완 |
| 9 | 답변 + 인용 렌더링 | ✅ | 파일명, 유형, 경고, 인용문 |
| 10 | 메트릭 + task_log 기록 | ✅ | task_log 기록 + 11개 메트릭 전체 emit 확인 |

### Section 9: 모델 전략

| Feature | Status | Notes |
|---|---|---|
| 14B 기본 + 상위 승격 | ✅ | qwen3:14b 기본, governor 승격 제어 |
| 후보 모델 3종 (Qwen3-14B, EXAONE, Kanana) | ✅ | 양쪽 백엔드에 alias 등록 |
| 30B 상시 상주 금지 | ✅ | battery/pressure 시 deep 차단 |
| MLX primary | ✅ | Metal cache clear 포함 |
| llama.cpp fallback | ✅ | keep_alive=0 언로드 |

### Section 10: 보안/접근 제어

| Feature | Status | Notes |
|---|---|---|
| 레벨 0 — 텍스트 전용 | ✅ | KB 없으면 stub 모드 |
| 레벨 1 — 선택 폴더 읽기 | ✅ | watched_folders 제한 |
| 레벨 2 — 승인형 쓰기 | ✅ | `draft_export`만 승인 후 실제 쓰기 허용 |
| 레벨 3-4 (자동화) | ❌ | 명시적 제외 |
| 인용 필수 | ✅ | repl.py 인용 표시 |
| Hard kill (파괴 명령 차단) | ✅ | 파괴적/대량 삭제 요청 차단 |
| 연속 에러 임계치 | ✅ | 반복 오류 도구 차단, degraded/search-only, safe mode 구현 |

### Section 11: 인덱싱/최신성 정책

| Feature | Status | Notes |
|---|---|---|
| 선택 폴더만 수집 | ✅ | kb_path 제한 |
| 포맷별 파서 | ✅ | Tier 1-3 전체 |
| 바이너리/대용량 제외 | ✅ | _BINARY_EXTENSIONS + 1MB 프로브 |
| 증분 인덱싱 | ✅ | watchdog + 시작 시 stale 정리 |
| 메타데이터 우선, 임베딩 지연 | ✅ | 형태소/임베딩 backfill daemon 구현 |
| Freshness 점수 보정 | ✅ | 4단계 boost (+2%~+15%) |
| Tombstone | ✅ | 삭제 시 즉시 처리 |
| SSD 쓰기량 주간 기록 | ❌ | |
| 대화 로그 요약 계층 | ❌ | 원본만 저장 |

### Section 12: Governor 리소스 관리

| Feature | Status | Notes |
|---|---|---|
| 메모리/swap/CPU/thermal/battery 감지 | ✅ | psutil + pmset |
| 인덱싱 큐 길이 | ✅ | watcher pending event count를 Governor에 반영 |
| AC+idle → 상위 모델 허용 | ✅ | AC + idle + 저압 상태에서 deep tier 요청 |
| AC+work → 14B | ✅ | balanced tier |
| 배터리 → deep 차단 | ✅ | battery < 30% |
| Swap ≥4GB → unloaded | ✅ | |
| Swap ≥2GB → fast | ✅ | |
| Thermal serious → fast | ✅ | |
| Thermal critical → unloaded | ✅ | |
| TTFT 임계 → 컨텍스트 축소 | ✅ | 최근 TTFT 기준 context/chunk budget 축소 |
| Governor 상태별 chunk 수 조절 | ✅ | tier별 retrieved chunk budget 적용 |

### Section 13: 리스크 대응

| Risk | Status | Notes |
|---|---|---|
| 한국어 검색 정확도 | 🔧 | Kiwi O, reranker 유보 |
| 30B 메모리 압박 | ✅ | 14B 기본, governor 차단 |
| Stale index 오답 | ✅ | 해시 비교, tombstone, UI 경고 |
| 과도한 권한 요구 | ✅ | 선택 폴더만 |
| 배터리/발열 | ✅ | governor 정책 |
| 모델 품질 미달 | ✅ | 양쪽 백엔드, hot-swap |

---

## 3. 구현 명세 (TASK-9A8DC5D5) 검수

### 모듈 구조 (37개 파일)

| 모듈 | Status | Notes |
|---|---|---|
| contracts/ (models, protocols, states, errors) | ✅ | 전체 구현 |
| core/ (orchestrator, governor, planner, tool_registry) | ✅ | 전체 구현 |
| retrieval/ (query_decomposer, fts_index, vector_index, hybrid_search, evidence_builder, freshness, tokenizer_kiwi) | ✅ | FTS + LanceDB vector + RRF + freshness 구현 |
| indexing/ (parsers, chunker, file_watcher, index_pipeline, tombstone) | ✅ | 전체 구현 |
| runtime/ (mlx_runtime, mlx_backend, llamacpp_backend, model_router, embedding_runtime) | 🔧 | model_router/embedding 구현, 다만 Governor 연동 및 운영 하드닝은 부분 구현 |
| memory/ (conversation_store, task_log) | ✅ | 전체 구현 |
| tools/ (read_file, search_files, draft_export) | ✅ | 3개 도구 모두 구현 및 등록 가능 |
| cli/ (repl, approval) | ✅ | approval이 export 흐름과 연동됨 |
| app/ (bootstrap, config) | ✅ | 전체 구현 |
| observability/ (metrics, tracing, health) | 🔧 | tracing/health 구현, 외부 export 및 운영 세분화는 부분 구현 |
| sql/schema.sql | ✅ | 5 테이블 + FTS5 + 트리거 |
| docs/DECISIONS.md | ✅ | 생성됨 |
| docs/IMPLEMENTATION_PLAN.md | ✅ | 생성됨 |

### 프로토콜 구현 현황 (12개)

| Protocol | Impl | Check |
|---|---|---|
| QueryDecomposerProtocol | QueryDecomposer | ✅ |
| FTSRetrieverProtocol | FTSIndex | ✅ |
| VectorRetrieverProtocol | VectorIndex | ✅ |
| HybridFusionProtocol | HybridSearch | ✅ |
| EvidenceBuilderProtocol | EvidenceBuilder | ✅ |
| LLMGeneratorProtocol | MLXRuntime | ✅ |
| LLMBackendProtocol | MLXBackend, LlamaCppBackend | ✅ |
| EmbeddingRuntimeProtocol | EmbeddingRuntime | ✅ |
| GovernorProtocol | Governor, GovernorStub | ✅ |
| ConversationStoreProtocol | ConversationStore | ✅ |
| TaskLogStoreProtocol | TaskLogStore | ✅ |
| ToolRegistryProtocol | ToolRegistry | ✅ |
| ApprovalGatewayProtocol | CLIApprovalGateway | ✅ |

### 장애 처리 (Section 13)

| 장애 모드 | Status | Notes |
|---|---|---|
| 모델 로드 실패 1회 재시도 | ✅ | MLX 1회 재시도 후 Ollama fallback |
| 모델 2회 연속 실패 → degraded | ✅ | `core/error_monitor.py` |
| 모델 3회 연속 → 검색 전용 | ✅ | `core/error_monitor.py`, `core/orchestrator.py` |
| SQLite 락 읽기 재시도 | ✅ | FTS 검색에서 짧은 재시도 후 실패 기록 |
| SQLite 무결성 실패 → 읽기 전용 | ✅ | read-only + rebuild flag |
| 임베딩 백로그 최근 우선 | ✅ | `updated_at DESC` recent-first 처리 |
| STALE 경고 + 기존 색인 사용 | ✅ | 해시 비교 |
| ACCESS_LOST 상태 | ✅ | |
| 5분 내 5에러 → 도구 중단 | ✅ | `core/error_monitor.py`, `core/tool_registry.py` |
| 10분 내 이중 실패 → safe mode | ✅ | `core/error_monitor.py`, `core/orchestrator.py` |

### 테스트 전략

| Test Layer | Status | Notes |
|---|---|---|
| tests/contracts/ | ✅ | 프로토콜, 모델, 상태, 에러, 아키텍처 적합성 |
| tests/unit/ | 🔧 | metrics, orchestrator, conversation, task_log 존재 |
| tests/integration/ | 🔧 | schema 테스트만 존재 |
| tests/perf/ | ✅ | benchmark 하네스 + report 검증 |
| tests/e2e/ | ✅ | smoke + orchestrator 통합 |
| 90% branch coverage | ❌ | coverage 설정 없음 |

### Degradation Matrix (Section 15)

| 조건 | Status | Notes |
|---|---|---|
| elevated: 10 chunks, max context | ✅ | deep tier 10 chunks / 16K window |
| baseline: 8 chunks, standard | ✅ | balanced tier 8 chunks / 8K window |
| degraded: 4 chunks, reduced | ✅ | fast tier 4 chunks / 4K window |
| thermal 상승 시 인덱싱 백오프 | ✅ | fair/serious 상태에서 backoff/pause |
| 배터리 모드 인덱싱 중지 | ✅ | 저배터리 비AC 상태에서 pause |
| swap 감지 시 상위 승격 금지 | ✅ | governor 구현 |

---

## 4. 주요 미구현 항목 (우선순위순)

### P0 — 핵심 기능 Gap

| 항목 | 명세 위치 | 현재 상태 | 영향 |
|------|-----------|-----------|------|
| **벡터 인덱스 (LanceDB + BGE-M3)** | Sec 5, 7, 9 | ✅ 구현 | semantic 검색 경로 사용 가능 |
| **임베딩 런타임** | Sec 7, 9 | ✅ 구현 | BGE-M3 기반 임베딩 생성 가능 |
| **ModelRouter 순차 로딩** | Sec 4, 9 | ✅ 구현 | 단일 활성 모델 + 메모리 버짓 체크 |
| **대화 히스토리 → LLM 컨텍스트** | Sec 8 step 5 | ✅ | 최근 3턴 슬라이딩 윈도우 반영 |

### P1 — 안정성/운영 Gap

| 항목 | 명세 위치 | 현재 상태 |
|------|-----------|-----------|
| Governor → chunk 수/컨텍스트 크기 조절 | Sec 12, 15 | ✅ |
| 연속 에러 카운터 (모델 2회, SQLite 3회) | Sec 10.3, 13 | ✅ degraded/write-block 기본 구현 |
| Safe mode (모델+인덱스 동시 실패) | Sec 13 | ✅ |
| 인덱싱 thermal/battery 백오프 | Sec 12.2 | ✅ |
| AC 전원 시 상위 모델 승격 허용 | Sec 12.2 | ✅ |

### P2 — 관측성/도구 Gap

| 항목 | 명세 위치 | 현재 상태 |
|------|-----------|-----------|
| 11개 메트릭 전체 emit | Sec 12 | ✅ 전체 emit 경로 확인 (query_latency, ttft, retrieval_top5_hit, citation_missing/stale_rate, trust_recovery, index_lag, swap, model_load_failure, sqlite_lock, draft_export_approval) |
| 구조화된 JSON 로깅 | Sec 12 | ✅ JsonLogFormatter 구현 |
| Health check 확장 | Sec 12 | ✅ core(db/metrics/folders/export) + runtime(model/embedding/vector_db/watcher/governor) 9개 체크 |
| 선택적 의존성 graceful degradation | Sec 11 | ✅ pymupdf/openpyxl/python-docx/python-pptx/hwpx/hwp5txt 미설치 시 로깅 후 건너뜀 |
| 마이크 권한 사전 점검 | Sec 10 | ✅ check_microphone_access() TCC pre-flight |
| Tool 실행 (read_file, search_files, draft_export) | Sec 8.2, 10 | ✅ |
| 50-query 벤치마크 하네스 | Sec 16 | ✅ `perf/benchmark.py`, `tests/perf/test_benchmark.py` |

### P3 — 명세 정합성 (이름/타입 불일치)

| 항목 | 명세 값 | 구현 값 |
|------|---------|---------|
| Governor tier 이름 | baseline/elevated/degraded | fast/balanced/deep/unloaded |
| TypedQueryFragment.kind | symbol/literal/prose | keyword/semantic |
| 6개 dataclass 이름 | UserQuery, RankedChunk 등 | str, HybridSearchResult 등 |
| DDL 컬럼명 다수 | file_path, mtime_epoch_ms | path, modified_at |

---

## 5. Phase 진행도

```
Phase 0 ██████████████████████ 100%  (핵심 하네스 포함)
Phase 1 ██████████████████████ 100%  (핵심 운영 항목 + 관측성/안전 완성)
Phase 2 ███████████████████░░ 90%   (STT/TTS + 메뉴바 + voice + health + 네이티브 녹음 + 장치 선택 + think 필터 + 동적 토큰 + 출처 임계값)
```

### 2026-03-21 Phase 2 진행 항목
- 네이티브 마이크 녹음: AVCaptureSession → AVAudioEngine (포맷 자동 변환)
- Two-Stage VAD: 적응형 노이즈 플로어 + IDLE→LISTENING→TENTATIVE→CONFIRMED 상태 머신
- CoreAudio 장치 열거 (AVCaptureDevice 제거 — aggregate device 블록 방지)
- audio-input entitlement + TCC 권한 처리
- 마이크 장치 선택 + Unicode NFC/NFD 정규화
- `<think>` 태그 필터링
- 동적 max_tokens 계산 (context_window - prompt_tokens - reserve)
- 출처 표시 relevance 임계값 (MIN_RELEVANCE_SCORE = 0.15)
- 긴 응답 임시 파일 저장 + ...more 버튼
- 인라인 export 패널 (창 사라짐 방지)
- transcribe-file 브리지 커맨드
- Ollama streaming (stream:true + 청크 파싱)
- Quit JARVIS 버튼 (⌘Q)
- Xcode 프로젝트 (JarvisMenuBar.xcodeproj) 추가

---

## 6. 2026-03-19 오전 세션에서 수정된 항목

| 수정 항목 | 파일 | 내용 |
|-----------|------|------|
| 선택적 의존성 fallback | `parsers.py` | pymupdf/openpyxl/python-docx/python-pptx/hwpx ImportError 가드 + hwp5txt 사전 체크 |
| Health check 확장 | `health.py` | model/embedding/vector_db/file_watcher/governor 5개 runtime 체크 추가, core/runtime 분리 |
| 마이크 권한 사전 점검 | `audio_recorder.py` | check_microphone_access() TCC pre-flight (macOS afrecord probe) |
| Voice session polish | `voice_session.py` | 마이크 권한 체크 연동, VAD Phase 2 deferral 문서화 |
| 테스트 보강 | `test_observability.py`, `test_audio_recorder.py` | health runtime 테스트 3개 + mic check 테스트 3개 추가 (334 passed) |

## 7. 2026-03-18 세션에서 수정된 항목

| 수정 항목 | 파일 | 내용 |
|-----------|------|------|
| Qwen3 thinking 비활성화 | `llamacpp_backend.py` | `think: false` 추가 |
| 기본 모델 변경 | `__main__.py` | qwen3:30b-a3b → qwen3:14b |
| PPTX 파서 추가 | `parsers.py`, `pyproject.toml` | python-pptx 기반 슬라이드 파싱 |
| 텍스트 자동감지 | `parsers.py` | is_indexable(), is_text_file() |
| 84개 확장자 등록 | `parsers.py` | 코드/데이터/웹/설정 파일 |
| Windows 인코딩 지원 | `parsers.py` | BOM 감지, CP949/EUC-KR/UTF-16 LE |
| 파일 이동/삭제 처리 | `file_watcher.py`, `index_pipeline.py` | on_moved, dir_deleted, dir_moved |
| 시작 시 stale 정리 | `__main__.py` | 파일 없는 document 자동 tombstone |
| SQL 파서 구조화 | `parsers.py` | 컬럼 정의 테이블 추출, GO 노이즈 제거 |
| Freshness STALE 자동감지 | `freshness.py` | SHA-256 해시 비교 |
| Freshness 점수 보정 | `freshness.py`, `evidence_builder.py` | 4단계 시간 기반 boost |
| 한국어 경고 메시지 | `repl.py` | STALE/MISSING/ACCESS_LOST 한국어화 |
| 인덱싱 에러 표시 | `__main__.py` | print 추가 (logging.ERROR에 묻히지 않도록) |
