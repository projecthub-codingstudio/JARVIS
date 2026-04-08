# JARVIS 질의-응답 파이프라인 아키텍처

> 최종 업데이트: 2026-04-08

---

## 1. 전체 흐름 개요

```
사용자 입력
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  프론트엔드 (React + TypeScript)                          │
│  App.tsx → useJarvis.ts → apiClient.ask()                │
│  + documentContextPaths (문서 컨텍스트 뱃지)               │
└────────────────────┬────────────────────────────────────┘
                     │ POST /api/ask
                     │ {text, session_id, context_document_paths?}
                     ▼
┌─────────────────────────────────────────────────────────┐
│  백엔드 (Python FastAPI)                                  │
│  web_api.py → JarvisApplicationService.handle()          │
│                                                          │
│  ┌─── 라우팅 분기 ─────────────────────────────┐         │
│  │                                              │         │
│  │  문서 컨텍스트 있음? ──→ 경로 A (직접 LLM)    │         │
│  │       아니오 ↓                               │         │
│  │  Builtin 매칭?    ──→ 경로 B (doc_find 등)   │         │
│  │       아니오 ↓                               │         │
│  │  RAG 파이프라인   ──→ 경로 C (검색 + LLM)     │         │
│  └──────────────────────────────────────────────┘         │
└────────────────────┬────────────────────────────────────┘
                     │ JSON response
                     ▼
┌─────────────────────────────────────────────────────────┐
│  프론트엔드 렌더링                                        │
│  answer.text → ReactMarkdown → 터미널 표시               │
│  guide.artifacts → 문서 카드 / Documents 뷰              │
│  guide.ui_hints → 뷰 전환 / 뱃지 설정                    │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 데이터 저장소 아키텍처

### 2.1 SQLite 데이터베이스

JARVIS의 모든 구조화 데이터를 저장하는 핵심 DB입니다.

```
~/.jarvis/jarvis.db (또는 JARVIS_DATA_DIR 설정값)
│
├── documents              ← 인덱싱된 문서 메타데이터
├── chunks                 ← 문서를 분할한 텍스트 청크
├── chunks_fts             ← FTS5 전문검색 인덱스
├── session_events         ← 학습용 세션 이벤트
├── learned_patterns       ← 학습된 쿼리 패턴
├── conversations          ← 대화 이력
├── task_logs              ← 작업 로그
├── user_knowledge         ← 사용자 지식 (Tier 3)
├── search_feedback        ← 피드백 데이터 (👍/👎)
└── query_document_affinity ← 학습된 쿼리-문서 연결
```

#### documents 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| document_id | TEXT PK | 문서 고유 ID |
| path | TEXT | 파일 절대 경로 |
| content_hash | TEXT | SHA256 해시 (변경 감지) |
| size_bytes | INTEGER | 파일 크기 |
| indexing_status | TEXT | `INDEXED` / `INDEXING` / `FAILED` |
| created_at | TEXT | 최초 인덱싱 시각 |
| updated_at | TEXT | 마지막 업데이트 시각 |

#### chunks 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| chunk_id | TEXT PK | 청크 고유 ID |
| document_id | TEXT FK | 소속 문서 ID |
| chunk_index | INTEGER | 문서 내 순서 |
| text | TEXT | 청크 텍스트 내용 |
| heading_path | TEXT | 섹션 경로 (예: `# 제목 > ## 소제목`) |
| lexical_morphs | TEXT | Kiwi 형태소 분석 결과 (FTS용) |
| embedding_ref | TEXT | LanceDB 벡터 참조 ID |

#### chunks_fts (FTS5 가상 테이블)

```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    lexical_morphs,
    content='chunks',
    content_rowid='rowid'
);
```

- `text`: 원본 텍스트 (영문/숫자 기반 검색)
- `lexical_morphs`: Kiwi 형태소 분석 결과 (한국어 검색)
- BM25 랭킹 알고리즘으로 점수 계산

#### search_feedback 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| feedback_id | TEXT PK | 피드백 고유 ID |
| query_text | TEXT | 원본 질문 |
| feedback_type | TEXT | `positive` / `negative` |
| relevant_paths | TEXT (JSON) | 유용한 문서 경로 목록 |
| irrelevant_paths | TEXT (JSON) | 무관한 문서 경로 목록 |
| citation_paths | TEXT (JSON) | 응답에 사용된 citation 경로 |
| session_id | TEXT | 세션 ID |
| created_at | REAL | Unix timestamp |

#### query_document_affinity 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| query_pattern | TEXT | 정규화된 쿼리 패턴 |
| document_path | TEXT | 문서 절대 경로 |
| affinity_score | REAL | 연관도 점수 (0.0~1.0) |
| hit_count | INTEGER | 양성 피드백 횟수 |
| last_updated | REAL | 마지막 업데이트 시각 |
| **PK** | | (query_pattern, document_path) |

### 2.2 LanceDB 벡터 데이터베이스

```
~/.jarvis/vectors.lance/
└── chunk_embeddings/      ← 테이블
     ├── data/             ← Arrow IPC 파일 (벡터 데이터)
     └── _versions/        ← 버전 관리
```

#### chunk_embeddings 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| chunk_id | STRING | SQLite chunks.chunk_id 참조 |
| document_id | STRING | SQLite documents.document_id 참조 |
| vector | VECTOR[1024] | BGE-M3 임베딩 벡터 |

- **임베딩 모델**: BGE-M3 (sentence-transformers, CPU)
- **벡터 차원**: 1024
- **거리 메트릭**: L2 (유클리디안)
- **검색**: ANN (Approximate Nearest Neighbor)
- **현재 규모**: 22,692개 벡터

### 2.3 Knowledge Base 파일 시스템

```
knowledge_base/                    ← JARVIS_KNOWLEDGE_BASE 환경변수 또는 자동 탐색
├── coding/                        ← 소스 코드
│   ├── ProjectHubApp.swift
│   ├── ProjectHubNetworkManager.swift
│   └── pipeline.py
├── 전자책/                         ← PDF 문서
│   ├── Effective_Modern_C__.pdf
│   └── Blazor/...
├── HTML/                          ← 웹 문서
├── shell/                         ← 스크립트
├── sql/                           ← SQL 파일
├── ProjectHub_Brochure.pptx       ← 프레젠테이션
├── 14day_diet_supplements_final.xlsx  ← 스프레드시트
└── ...
```

---

## 3. 인덱싱 파이프라인

문서가 knowledge_base에 추가되면 자동으로 인덱싱됩니다.

```
파일 감지 (FileWatcher / 수동 reindex)
    │
    ▼
┌─────────────────────────────────────────────┐
│ Step 1: 문서 파싱 (DocumentParser)            │
│                                              │
│  확장자별 파서:                                │
│  .md/.txt    → 텍스트 직접 읽기               │
│  .py/.js/.ts → 코드 파서 (AST)               │
│  .pdf        → PDF 파서 (pdfminer)           │
│  .docx       → python-docx                   │
│  .pptx       → python-pptx                   │
│  .xlsx       → openpyxl                      │
│  .hwp/.hwpx  → hwp5 파서                     │
│  .html       → HTML 파서                     │
│                                              │
│  → ParsedDocument (DocumentElement 리스트)    │
└──────────────┬──────────────────────────────┘
               ▼
┌─────────────────────────────────────────────┐
│ Step 2: 청킹 (ChunkRouter)                   │
│                                              │
│  타입별 전략:                                  │
│                                              │
│  ┌─ ParagraphChunkStrategy ──────────────┐  │
│  │  max: 500 토큰 (~1500자)               │  │
│  │  overlap: 80 토큰 (~240자)             │  │
│  │  heading 추적: # → ## → ### 경로       │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  ┌─ TableChunkStrategy ──────────────────┐  │
│  │  요약 청크: "Table with N rows..."     │  │
│  │  행별 청크: "header1=val | header2=val" │  │
│  │  heading: table-row-SheetName-N       │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  ┌─ CodeChunkStrategy ───────────────────┐  │
│  │  1차: tree-sitter AST 파싱             │  │
│  │       (Python, JS, TS 지원)            │  │
│  │  2차: regex fallback (class, def)      │  │
│  │  max: 1500자, 함수/클래스 단위 분할     │  │
│  │  heading: code:python, code:swift      │  │
│  └───────────────────────────────────────┘  │
└──────────────┬──────────────────────────────┘
               ▼
┌─────────────────────────────────────────────┐
│ Step 3: 저장 (IndexPipeline)                  │
│                                              │
│  SQLite:                                     │
│    documents INSERT (status=INDEXING)         │
│    chunks INSERT (text, heading_path)         │
│    documents UPDATE (status=INDEXED)          │
│                                              │
│  비동기 백필 (Deferred Backfill):              │
│                                              │
│  ┌─ backfill_morphemes ──────────────────┐  │
│  │  Kiwi 형태소 분석                       │  │
│  │  NNG/NNP/VV/VA 태그 추출               │  │
│  │  → chunks.lexical_morphs 업데이트       │  │
│  │  batch_size: 100                       │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  ┌─ backfill_embeddings ─────────────────┐  │
│  │  BGE-M3 임베딩 생성 (CPU)              │  │
│  │  → LanceDB chunk_embeddings INSERT     │  │
│  │  → chunks.embedding_ref 업데이트        │  │
│  │  batch_size: 32                        │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 청크 예시

**원본 문서** (ProjectHubNetworkManager.swift, 500줄):
```
┌──────────────────────────────────┐
│ import Foundation                 │  ← chunk_0 (코드: import + class 선언)
│ import Network                    │     heading: "code:swift"
│                                   │     ~800자
│ class ProjectHubNetworkManager {  │
│   enum ConnectionState { ... }    │
│   ...                             │
├──────────────────────────────────┤
│ func startHost() {                │  ← chunk_1 (코드: startHost 함수)
│   ...                             │     heading: "code:swift"
│ }                                 │     ~1200자
├──────────────────────────────────┤
│ func connect(to:) {               │  ← chunk_2 (코드: connect 함수)
│   ...                             │     heading: "code:swift"
│ }                                 │     ~900자
├──────────────────────────────────┤
│ ...                               │  ← chunk_3~N (나머지 함수들)
└──────────────────────────────────┘
```

**원본 문서** (14day_diet_supplements_final.xlsx):
```
┌──────────────────────────────────┐
│ [Sheet1] Table with 14 rows.     │  ← chunk_0 (테이블 요약)
│ Columns: Day, 아침, 점심, 저녁   │     heading: "table-summary-Sheet1"
├──────────────────────────────────┤
│ Day=1 | 아침=오트밀 |             │  ← chunk_1 (1일차 행)
│ 점심=닭가슴살 | 저녁=연어         │     heading: "table-row-Sheet1-1"
├──────────────────────────────────┤
│ Day=2 | 아침=그래놀라 |           │  ← chunk_2 (2일차 행)
│ 점심=소고기 | 저녁=두부           │     heading: "table-row-Sheet1-2"
├──────────────────────────────────┤
│ ...                               │  ← chunk_3~14 (3~14일차)
└──────────────────────────────────┘
```

---

## 4. 경로별 상세 흐름

### 경로 A: 문서 컨텍스트 직접 LLM

뷰어에서 질문하거나, doc_find 후 뱃지가 연결된 상태에서 질문할 때 사용됩니다.

```
context_document_paths 존재
    │
    ▼
_ask_about_documents(query, paths)
    │
    ├─ 1. 파일 읽기
    │     각 경로 → resolve (절대 경로 / KB 상대 경로)
    │     텍스트 파일 (.py, .swift, .md 등) → 직접 read
    │     바이너리 (.pdf, .docx 등) → indexed chunks 조합
    │     파일당 예산: context_window ÷ 3 ÷ 파일수 × 3 chars/token
    │
    ├─ 2. LLM 백엔드 선택
    │     ┌─ _get_doc_analysis_backend() ──────────┐
    │     │  1차: Gemma 4 E4B (128K context)        │
    │     │       싱글턴 캐시 (_doc_backend_instance) │
    │     │  2차: Runtime context의 EXAONE fallback  │
    │     └────────────────────────────────────────┘
    │
    ├─ 3. 프롬프트 구성
    │     시스템: _DOCUMENT_ANALYSIS_SYSTEM_PROMPT
    │       "사용자의 질문에 자연스럽게 답변하세요"
    │       "코드 분석이면 상세하게, 인사면 자연스럽게"
    │     컨텍스트: "[파일: name]\n{내용}" × N개 파일
    │     프롬프트: 사용자 질문 그대로 (LLM이 유형 판단)
    │
    ├─ 4. 생성 + 이어쓰기
    │     _generate_full_response()
    │       → _generate_single_chunk()
    │       → 잘림 감지 (response_chars > context_window × 0.8)
    │       → 최대 3회 continuation (이전 응답을 컨텍스트로)
    │
    └─ 5. 응답 조립
          _response_payload() 형식
          artifacts: 참조 파일 목록
          citations: 파일명 + 경로
          ※ RAG 파이프라인 완전 우회
```

### 경로 B: Builtin Capability

정규식 패턴으로 매칭되는 즉답형 기능입니다.

```
resolve_builtin_capability(text)
    │
    ├─ _DOC_FIND_RE     ──→ _build_doc_find_response()
    │   "문서 찾아/보여/알려"    검색어 추출 (filler 제거)
    │                          Pass 1: KB 상대경로 매칭 (ALL terms)
    │                          Pass 2: FTS OR 내용 매칭 (항상 실행)
    │                          → preferred_view: "documents"
    │
    ├─ _DIRECT_URL_RE   ──→ 웹사이트 직접 열기
    ├─ _CALC_HINT_RE    ──→ 수학 계산
    ├─ _TIME_QUERY_RE   ──→ 시간/날짜
    ├─ _WEATHER_QUERY_RE──→ 날씨
    ├─ _HELP_QUERY_RE   ──→ 도움말
    ├─ calendar_*       ──→ 캘린더 (생성/조회/수정)
    ├─ doc_summary      ──→ 문서 요약
    ├─ doc_outline      ──→ 문서 목차
    ├─ doc_sheet        ──→ 스프레드시트 시트
    └─ open_document    ──→ 문서 열기
    
    ※ 매칭되면 즉시 반환, RAG 도달하지 않음
```

### 경로 C: RAG 파이프라인

일반 질문에 대한 검색 증거 기반 답변 생성입니다.

```
_run_menu_bridge_ask_with_fallback(query)
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ Step 1: Planner (쿼리 분석)                            │
│                                                       │
│  HeuristicPlanner.analyze()                           │
│    ├─ intent 분류: qa / smalltalk / weather / ...     │
│    ├─ retrieval_task: document_qa / table_lookup /     │
│    │                  code_lookup / multi_doc_qa       │
│    ├─ search_terms: ["키워드1", "키워드2"]              │
│    ├─ target_file: "파일명.ext" (언급 시)              │
│    └─ confidence: 0.45 ~ 1.0                          │
│                                                       │
│  LightweightKeywordExpander (이중언어 확장)             │
│    _BILINGUAL_EXPANSIONS (95쌍):                       │
│    "네트워크" → ["network", "networking"]              │
│    "클래스"   → ["class"]                              │
│    "매니저"   → ["manager"]                            │
│    "데이터베이스" → ["database", "db"]                  │
│                                                       │
│  LearningCoordinator.inject_hints()                   │
│    학습된 entity hints 주입 (cosine ≥ 0.75)            │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ Step 2: Query Decomposition                           │
│                                                       │
│  QueryDecomposer.decompose(query)                     │
│    ├─ 언어 감지: ko / en / code                       │
│    ├─ 한국어: Kiwi 형태소 + 어휘 복원                   │
│    ├─ 코드: 식별자 복원 (ASR 보정)                      │
│    └─ TypedQueryFragment 생성:                         │
│         keyword (weight=1.0): 추출된 키워드             │
│         semantic (weight=0.7): 전체 쿼리 (벡터용)       │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ Step 3: 병렬 검색                                      │
│                                                       │
│  ThreadPoolExecutor(max_workers=2)                    │
│                                                       │
│  ┌─ FTS 검색 ──────────────────┐ ┌─ Vector 검색 ──┐  │
│  │ SQLite FTS5                  │ │ BGE-M3 임베딩   │  │
│  │                              │ │ (1024차원, CPU) │  │
│  │ 한국어: Kiwi 형태소           │ │                 │  │
│  │   NNG(명사) NNP(고유명사)     │ │ LanceDB ANN    │  │
│  │   VV(동사) VA(형용사)         │ │ 검색            │  │
│  │ 영어: whitespace split       │ │                 │  │
│  │                              │ │ score =         │  │
│  │ BM25 랭킹                    │ │ 1.0 - distance  │  │
│  │ top_k = 16                   │ │ top_k = 16      │  │
│  └─────────────┬────────────────┘ └───────┬─────────┘  │
│                └──────────┬───────────────┘             │
│                           ▼                             │
│              Hybrid Fusion (RRF)                        │
│              ┌─────────────────────────────┐            │
│              │ k = 60                       │            │
│              │ vector_weight = 2.0          │            │
│              │                              │            │
│              │ FTS rank 1:  1/(60+1) = 0.016│            │
│              │ Vec rank 1: 2/(60+1) = 0.033│            │
│              │ Both rank 1: 합계 = 0.049    │            │
│              └─────────────────────────────┘            │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ Step 4: Strategy Augmentation                         │
│                                                       │
│  retrieval_task에 따른 전략 선택:                        │
│                                                       │
│  DocumentStrategy (기본):                              │
│    ├─ 파일명 매칭 → 해당 파일 chunks 우선 (+10.0)       │
│    ├─ 클래스/함수 시그니처 부스트 (+12.0/+10.0)          │
│    └─ 섹션/토픽 heading 매칭                            │
│                                                       │
│  TableStrategy:                                       │
│    ├─ row_id 매칭 → 행 chunks 우선 (+50.0)             │
│    └─ field 매칭 → 행+필드 교차 (+100.0)                │
│                                                       │
│  CodeStrategy (extends Document):                     │
│    └─ 코드 파일 우선 + 식별자 부스트                     │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ Step 5: Reranker (Cross-Encoder)                      │
│                                                       │
│  모델: mmarco-mMiniLMv2-L12-H384-v1                  │
│  디바이스: CPU (Metal 충돌 방지)                         │
│  입력: (query, chunk_full_text) 쌍 16개                │
│  batch_size: 16                                       │
│                                                       │
│  점수 계산:                                             │
│    ce_norm = sigmoid(ce_raw_logit)     ← [0, 1] 정규화│
│    combined = 0.7 × ce_norm                           │
│             + 0.3 × min(1.0, rrf_score × 60)          │
│                                                       │
│  → 상위 8개 선택 (max_retrieved_chunks)                │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ Step 6: Evidence Builder (증거 구성)                    │
│                                                       │
│  부스트 체계:                                           │
│  ┌──────────────────────┬───────┬──────────────────┐  │
│  │ 조건                  │ 부스트 │ 설명              │  │
│  ├──────────────────────┼───────┼──────────────────┤  │
│  │ 파일명 정확 매칭       │ +0.20 │ 쿼리에 파일명 포함 │  │
│  │ 파일명 stem 매칭      │ +0.15 │ 확장자 없이 매칭   │  │
│  │ 코드 쿼리+코드 파일    │ +0.28 │ 코드 질문 우대     │  │
│  │ 클래스 시그니처        │ +0.16 │ class Name 매칭   │  │
│  │ 함수 시그니처          │ +0.12 │ def/function 매칭  │  │
│  │ 식별자 매칭            │ +0.08 │ 코드 이름 포함     │  │
│  │ 문서 구문 매칭         │ +0.08 │ bi/trigram 매칭   │  │
│  │  └ 강한 구문          │ +0.16 │ 3+ gram 매칭      │  │
│  │ 설명적 텍스트          │ +0.05 │ "~이다/있다/한다"  │  │
│  │ 최근 수정 (1시간)      │ +0.15 │ freshness tier    │  │
│  │ 최근 수정 (1일)        │ +0.10 │                   │  │
│  │ 최근 수정 (3일)        │ +0.05 │                   │  │
│  │ 최근 수정 (7일)        │ +0.02 │                   │  │
│  │ 피드백 affinity        │ +0.20 │ 학습된 연관도 (max)│  │
│  │ 코드 쿼리+비코드 파일   │ -0.14 │ 패널티            │  │
│  │ 참조 텍스트            │ -0.12 │ "참조" 패널티      │  │
│  └──────────────────────┴───────┴──────────────────┘  │
│                                                       │
│  Freshness 검증: SHA256 해시 비교                       │
│    VALID: 해시 일치 (문서 변경 없음)                     │
│    STALE: 해시 불일치 (문서가 수정됨)                     │
│    MISSING: 파일 없음                                   │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ Step 7: Answerability Gate (답변 가능성 판단)            │
│                                                       │
│  ┌─────────────────────────────────────────┐          │
│  │ top_score < 0.08 AND overlap < 0.34     │          │
│  │  → ABSTAIN (답변 거부)                   │          │
│  │    "근거가 부족하여 답변할 수 없습니다"     │          │
│  │                                          │          │
│  │ target_file 지정 but 미발견              │          │
│  │  → ABSTAIN (confidence 0.93)             │          │
│  │                                          │          │
│  │ top-2 점수 차이 ≤ 0.08 AND 유사 overlap  │          │
│  │  → CLARIFY (명확화 요청)                  │          │
│  │    "어느 문서를 말씀하시는지 알려주세요"    │          │
│  │                                          │          │
│  │ 그 외                                    │          │
│  │  → ANSWER (답변 진행)                     │          │
│  └─────────────────────────────────────────┘          │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ Step 8: LLM Generation (답변 생성)                     │
│                                                       │
│  시스템 프롬프트 구성:                                    │
│    SYSTEM_PROMPT                                      │
│      답변 규칙 (증거 기반, 추측 금지)                     │
│      응답 포맷 규칙 (질문 유형별 자동 선택):               │
│        구체적 값 → 값만 바로                              │
│        목록     → 번호/불릿                              │
│        비교     → markdown 표                           │
│        절차     → Step 1, 2, 3                         │
│        분석     → 구조화된 서술형                         │
│        코드     → 코드 블록                              │
│        확인     → 예/아니오                               │
│    + 페르소나 (JARVIS: 세련된 AI 어시스턴트 말투)          │
│    + 참고 증거 (검색된 chunks, max 16,384자)             │
│                                                       │
│  모델:                                                 │
│    기본: EXAONE-3.5-7.8B (MLX, 8K context)             │
│    문서 분석: Gemma 4 E4B (MLX-VLM, 128K context)       │
│                                                       │
│  max_tokens = context_window - prompt_tokens           │
│  temperature = 0.7                                    │
└──────────────────────────────────────────────────────┘
```

---

## 5. 프론트엔드 응답 처리

```
API 응답 수신 (useJarvis.ts)
    │
    ├─ response.answer.text
    │     → normalizeResponseText() (줄바꿈/인용부호 정리)
    │     → Message 객체로 저장
    │     → ReactMarkdown 렌더링 (표, 목록, 코드 블록 지원)
    │
    ├─ response.guide.artifacts
    │     → assets 상태 저장
    │     → 터미널: "Related Documents" 카드 표시
    │     → Documents 뷰: cascade 윈도우 배치
    │
    ├─ response.guide.ui_hints.preferred_view
    │     "documents" → documentContextPaths 설정 (뱃지 표시)
    │     "dashboard" → 터미널 포커스
    │     "repository" → Explorer 전환
    │
    ├─ response.guide.presentation
    │     → selected_artifact_id → 기본 선택 문서
    │     → blocks → 레이아웃 구조 (answer/list/detail)
    │
    ├─ response.response.citations
    │     → Source Map (radial 그래프, 최대 8개 + 오버플로우 리스트)
    │     → Evidence 패널 (citation quote 표시)
    │
    └─ response.guide.has_clarification
          → Clarification 프롬프트 표시 (추가 정보 요청)
```

---

## 6. 피드백 학습 루프

```
┌────────────────────────────────────────────────────────┐
│                   사용자 답변 확인                        │
│                         │                               │
│              ┌──────────┴──────────┐                    │
│              ▼                     ▼                    │
│           👍 클릭               👎 클릭                  │
│              │                     │                    │
│              ▼                     ▼                    │
│    POST /api/feedback       POST /api/feedback          │
│    type: "positive"         type: "negative"            │
│              │                     │                    │
│              ▼                     ▼                    │
│    search_feedback 저장     search_feedback 저장         │
│              │                                          │
│              ▼                                          │
│    query_document_affinity                              │
│    업데이트 (+0.1, max 1.0)                              │
│              │                                          │
│              ▼                                          │
│    다음 검색 시:                                         │
│    evidence_builder에서                                  │
│    affinity_score × 0.2 부스트                           │
│    (최대 +0.2)                                          │
│              │                                          │
│              ▼                                          │
│    ┌─────────────────────────┐                          │
│    │ 검색 품질 자동 향상       │                          │
│    │ 자주 유용한 문서 = 높은   │                          │
│    │ affinity = 더 높은 순위   │                          │
│    └─────────────────────────┘                          │
└────────────────────────────────────────────────────────┘
```

---

## 7. 설정값 요약

### 검색 파라미터

| 파라미터 | 값 | 위치 |
|---------|-----|------|
| FTS top_k | 16 | orchestrator.py |
| Vector top_k | 16 | orchestrator.py |
| Reranker 출력 | 8 (max_retrieved_chunks) | RuntimeDecision |
| RRF k | 60 | hybrid_search.py |
| RRF vector_weight | 2.0 | hybrid_search.py |
| CE weight | 0.7 | reranker.py |
| RRF weight | 0.3 | reranker.py |
| MIN_RELEVANCE_SCORE | 0.01 | evidence_builder.py |
| Context budget | 16,384 chars | context_assembler.py |

### 인덱싱 파라미터

| 파라미터 | 값 | 위치 |
|---------|-----|------|
| Chunk max tokens | 500 (~1500자) | chunker.py |
| Chunk overlap | 80 tokens (~240자) | chunker.py |
| Code chunk max | 1500자 | strategies/code.py |
| Embedding model | BGE-M3 (1024dim) | vector_index.py |
| Embedding device | CPU | EmbeddingRuntime |
| Morpheme backfill batch | 100 | index_pipeline.py |
| Embedding backfill batch | 32 | index_pipeline.py |

### LLM 모델

| 모델 | 용도 | Context | 속도 |
|------|------|---------|------|
| EXAONE-3.5-7.8B | 기본 RAG 답변 | 8K* | ~1.5초 |
| Gemma 4 E4B | 문서 직접 분석 | 128K | ~3초 |
| Gemma 4 E2B | (경량, 미사용) | 128K | 103 tok/s |

*RuntimeDecision 기본값. 모델 자체는 32K 지원.

### 학습 파라미터

| 파라미터 | 값 | 위치 |
|---------|-----|------|
| Batch 분석 주기 | 600초 | batch_scheduler.py |
| 재구성 감지 윈도우 | 300초 | coordinator.py |
| 패턴 매칭 임계값 | cosine ≥ 0.75 | coordinator.py |
| Affinity 증가량 | +0.1 / positive | web_api.py |
| Affinity 최대값 | 1.0 | web_api.py |
| Affinity 부스트 스케일 | × 0.2 | evidence_builder.py |

---

## 8. 주요 파일 맵

```
alliance_20260317_130542/src/jarvis/
├── web_api.py                          ← HTTP 엔드포인트 (FastAPI)
├── service/
│   ├── application.py                  ← 서비스 핵심 (라우팅, 문서 분석)
│   ├── builtin_capabilities.py         ← Builtin 기능 (doc_find 등)
│   └── protocol.py                     ← RPC 프로토콜
├── core/
│   ├── orchestrator.py                 ← RAG 오케스트레이터
│   ├── planner.py                      ← 쿼리 분석 + 이중언어 확장
│   └── answerability_gate.py           ← 답변 가능성 판단
├── retrieval/
│   ├── query_decomposer.py             ← 쿼리 분해
│   ├── fts_index.py                    ← FTS5 전문검색
│   ├── vector_index.py                 ← LanceDB 벡터 검색
│   ├── hybrid_search.py                ← RRF 하이브리드 합산
│   ├── strategy.py                     ← 검색 전략 (Document/Table/Code)
│   ├── reranker.py                     ← Cross-Encoder 리랭커
│   ├── evidence_builder.py             ← 증거 구성 + 부스트 + affinity
│   ├── freshness.py                    ← 문서 변경 감지
│   └── context_assembler.py            ← 컨텍스트 조립 (16K budget)
├── indexing/
│   ├── index_pipeline.py               ← 인덱싱 파이프라인
│   ├── chunk_router.py                 ← 청크 전략 라우팅
│   ├── chunker.py                      ← ParagraphChunkStrategy
│   ├── strategies/
│   │   ├── table.py                    ← TableChunkStrategy
│   │   └── code.py                     ← CodeChunkStrategy
│   └── file_watcher.py                 ← 파일 변경 감지
├── runtime/
│   ├── system_prompt.py                ← 시스템 프롬프트 (포맷 규칙)
│   ├── voice_persona.py                ← JARVIS 페르소나
│   ├── mlx_backend.py                  ← EXAONE MLX 백엔드
│   ├── mlx_runtime.py                  ← MLXRuntime (Generator 브릿지)
│   └── gemma_vlm_backend.py            ← Gemma 4 MLX-VLM 백엔드
├── learning/
│   ├── coordinator.py                  ← 학습 총괄
│   ├── reformulation_detector.py       ← 실패→성공 쌍 감지
│   ├── pattern_extractor.py            ← 패턴 분류
│   ├── pattern_matcher.py              ← 패턴 매칭 (cosine)
│   ├── pattern_store.py                ← SQLite 저장
│   └── batch_scheduler.py              ← 10분 주기 분석
├── app/
│   ├── bootstrap.py                    ← DB 초기화 + 마이그레이션
│   ├── config.py                       ← 설정
│   └── runtime_context.py              ← 런타임 컨텍스트 관리
└── contracts/
    ├── models.py                       ← 데이터 모델 (RuntimeDecision 등)
    └── protocols.py                    ← 프로토콜 인터페이스

ProjectHub-terminal-architect/src/
├── App.tsx                             ← 메인 앱 (뷰 전환, 상태 관리)
├── types.ts                            ← TypeScript 타입 정의
├── hooks/useJarvis.ts                  ← API 통신 훅
├── lib/
│   ├── api-client.ts                   ← HTTP 클라이언트
│   └── response-text.ts                ← 응답 텍스트 정규화
├── store/app-store.ts                  ← Zustand 상태 관리
├── components/
│   ├── documents/DocumentsWorkspace.tsx ← Documents 뷰 (cascade)
│   ├── explorer/
│   │   ├── ExplorerWorkspace.tsx        ← 파일 탐색기
│   │   └── ExplorerViewer.tsx           ← 플로팅 윈도우
│   ├── viewer/
│   │   ├── ViewerShell.tsx              ← 문서 뷰어 셸
│   │   └── ViewerRouter.tsx             ← 12개 렌더러 라우팅
│   ├── workspaces/
│   │   └── TerminalWorkspace.tsx        ← 터미널 (채팅 + 피드백)
│   └── shell/
│       └── CommandPalette.tsx           ← Cmd+K 명령 팔레트
└── ...
```
