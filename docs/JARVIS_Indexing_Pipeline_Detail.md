# JARVIS 인덱싱 파이프라인 상세 설명

> 최종 업데이트: 2026-04-08
>
> 지식저장소(Knowledge Base)의 파일이 어떻게 인덱싱되어 검색 가능한 상태가 되는지를 단계별로 설명합니다.

---

## 1. 전체 인덱싱 흐름

```
Knowledge Base 파일 변경 감지
    │
    ▼
┌───────────────────────────────────────────────────┐
│ Step 1: 파일 감지 (FileWatcher / Health Check)      │
│   watchdog PollingObserver → created/modified/deleted │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────┐
│ Step 2: 변경 판단 (SHA256 Hash)                     │
│   content_hash 비교 → 변경 없으면 SKIP              │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────┐
│ Step 3: 문서 파싱 (DocumentParser)                   │
│   확장자별 파서 → ParsedDocument (DocumentElement[]) │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────┐
│ Step 4: 청킹 (ChunkRouter)                          │
│   element_type별 전략 선택                           │
│   → ParagraphChunkStrategy (텍스트)                 │
│   → TableChunkStrategy (표)                         │
│   → CodeChunkStrategy (코드)                        │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────┐
│ Step 5: 즉시 저장 (SQLite)                          │
│   documents 테이블 → INDEXING → INDEXED              │
│   chunks 테이블 (text, heading_path)                 │
│   chunks_fts 자동 갱신 (FTS5 트리거)                  │
└───────────────┬───────────────────────────────────┘
                ▼
┌───────────────────────────────────────────────────┐
│ Step 6: 비동기 백필 (Deferred)                       │
│   6a. 형태소 분석 (Kiwi) → lexical_morphs            │
│   6b. 벡터 임베딩 (BGE-M3) → LanceDB                │
└───────────────────────────────────────────────────┘
```

---

## 2. Step 1: 파일 감지

### 2.1 FileWatcher (실시간 감시)

```python
# file_watcher.py
PollingObserver → _Handler(FileSystemEventHandler)
```

| 이벤트 | 처리 |
|--------|------|
| `on_created` | 새 파일 → `index_file(path)` |
| `on_modified` | 변경된 파일 → `index_file(path)` (hash 비교 후 재인덱싱) |
| `on_deleted` | 삭제된 파일 → `remove_file(path)` (tombstone 생성) |
| `on_moved` | 이동/이름변경 → `move_file(old, new)` (경로 업데이트 또는 재인덱싱) |

- **감시 방식**: `PollingObserver` (macOS FSEvents 대신 폴링, 안정성 우선)
- **무시 규칙**: `.`으로 시작하는 파일 (예: `.DS_Store`)
- **디렉토리 이벤트**: 디렉토리 삭제/이동 시 하위 모든 문서 일괄 처리

### 2.2 Health Check 자동 감지

```
GET /api/health 호출 시:
  → knowledge_base 디렉토리 스캔
  → DB에 없는 새 파일 감지
  → 백그라운드 인덱싱 트리거
```

### 2.3 수동 리인덱스

```
POST /api/reindex
  → 전체 knowledge_base 재스캔
  → 모든 파일 재인덱싱 (hash 변경된 것만)
```

---

## 3. Step 2: 변경 판단 (SHA256 Hash)

```python
# parsers.py → DocumentParser.create_record()
def create_record(path: Path) -> DocumentRecord:
    content = path.read_bytes()
    return DocumentRecord(
        document_id=uuid4(),
        path=str(path),
        content_hash=sha256(content).hexdigest(),  # ← 핵심
        size_bytes=len(content),
        indexing_status=IndexingStatus.PENDING,
    )
```

```python
# index_pipeline.py → index_file()
existing = find_document_by_path(path)
if existing
   and existing.content_hash == new_record.content_hash  # 해시 동일
   and existing.indexing_status == INDEXED:               # 이미 성공
    return existing  # ← SKIP (재인덱싱 불필요)
```

| 상황 | 동작 |
|------|------|
| 해시 동일 + INDEXED | 건너뜀 (변경 없음) |
| 해시 동일 + FAILED | 재시도 (이전 실패 복구) |
| 해시 다름 | 기존 chunks/vectors 삭제 → 재인덱싱 |
| 신규 파일 | 새로 인덱싱 |

---

## 4. Step 3: 문서 파싱 (DocumentParser)

### 4.1 파서 라우팅

```python
_EXTENSION_TYPE_MAP = {
    # 텍스트/마크다운
    ".md": "markdown",  ".txt": "text",  ".csv": "text",
    ".html": "text",    ".xml": "text",  ".css": "text",
    
    # 코드 (AST 지원)
    ".py": "python",    ".ts": "typescript",  ".js": "javascript",
    
    # 코드 (일반)
    ".swift": "code",   ".java": "code",  ".kt": "code",
    ".go": "code",      ".rs": "code",    ".cpp": "code",
    ".c": "code",       ".cs": "code",    ".rb": "code",
    ".sh": "code",      ".sql": "sql",
    
    # 데이터
    ".json": "json",    ".yaml": "yaml",
    
    # 바이너리 문서
    ".pdf": "pdf",      ".docx": "docx",  ".pptx": "pptx",
    ".xlsx": "xlsx",    ".hwpx": "hwpx",  ".hwp": "hwp",
}
```

**미등록 확장자** → 텍스트 자동 감지 (`is_text_file()`):
1. 바이너리 확장자(.png, .mp3 등) → 즉시 거부
2. 1MB 초과 → 거부
3. 첫 8KB 읽기 → BOM 확인 → null 바이트 검사 → 인코딩 감지
4. UTF-8 / CP949 / EUC-KR / Latin-1 순서로 시도

### 4.2 각 파서의 동작

#### 텍스트/마크다운 (text, markdown)

```
파일 읽기 (인코딩 자동 감지: UTF-8 → CP949 → EUC-KR → Latin-1)
    → DocumentElement(element_type="text", text=내용)
```

- BOM 감지: UTF-16 LE/BE, UTF-8 BOM 지원
- Windows 한글 파일(CP949/EUC-KR) 자동 처리

#### Python (python) / JavaScript / TypeScript

```
파일 읽기
    → DocumentElement(element_type="code", text=내용, metadata={"language": "python"})
```

- `element_type="code"` → CodeChunkStrategy로 라우팅
- 언어 정보가 metadata에 포함되어 tree-sitter AST 파싱에 사용

#### 일반 코드 (code) — Swift, Java, Go, C++ 등

```
파일 읽기
    → DocumentElement(element_type="code", text=내용, metadata={"language": ""})
```

- tree-sitter 미지원 언어 → regex fallback (`class `, `def `, `async def `)

#### PDF

```python
# _parse_pdf_structured() — PyMuPDF 사용

PDF 파일 열기 (pymupdf)
    │
    페이지별 처리:
    ├─ 1. 표 추출: page.find_tables()
    │     → DocumentElement(type="table", metadata={headers, rows, sheet_name})
    │
    └─ 2. 텍스트 블록 추출: page.get_text("blocks")
          → 표 영역 내 블록 제외
          → 작은 블록 병합 (min 200자)
          → DocumentElement(type="text", text=병합된텍스트)
    
    제한: 최대 500,000자 (초과 시 truncate)
```

**핵심**: 블록 레벨 추출로 미세 청크 문제 방지 (씨샵.pdf: 19,543 → 적정 수로 감소)

#### DOCX

```python
# _parse_docx() — python-docx 사용

DOCX 열기
    ├─ 단락 추출: doc.paragraphs → 텍스트
    └─ 표 추출: doc.tables → "셀1 | 셀2 | 셀3" 형식
```

#### PPTX

```python
# _parse_pptx() — python-pptx 사용

PPTX 열기
    슬라이드별:
    ├─ 텍스트 프레임: shape.text_frame → 텍스트
    ├─ 표: shape.table → "셀1 | 셀2" 형식
    └─ 노트: slide.notes_slide → "[Notes] 내용"
    
    → "[Slide N]\n텍스트\n표\n노트" 형식
```

#### XLSX

```python
# _parse_xlsx() — openpyxl 사용
# _parse_xlsx_structured() — 구조화 추출

시트별:
    첫 행 = 헤더
    나머지 = 데이터 행
    
    → DocumentElement(type="table", metadata={
        headers: ("Day", "아침", "점심", "저녁"),
        rows: (("1", "오트밀", "닭가슴살", "연어"), ...),
        sheet_name: "Sheet1"
    })
```

#### HWP / HWPX (한글 문서)

```
HWPX (XML 기반 ZIP):
    1차: hwpx 라이브러리 → TextExtractor
    2차: 직접 ZIP 압축 해제 → XML 파싱
    표: XML에서 <hp:tbl> 요소 추출 → DocumentElement(type="table")

HWP (레거시 바이너리):
    hwp5 파서 → 텍스트 추출 (포맷 손실 허용)
```

#### SQL

```python
# _parse_sql() — 구조화 추출

SQL 파일 읽기 (EUC-KR/CP949 인코딩 지원)
    ├─ CREATE TABLE 추출 → 테이블명, 컬럼 정의
    ├─ CREATE VIEW 추출
    ├─ CREATE INDEX 추출
    ├─ sp_addextendedproperty → 컬럼 설명(한글) 매핑
    └─ 구조화된 출력:
        "## 테이블: tbl_day_chart (일별 차트)\n"
        "| 컬럼 | 타입 | NULL | 설명 |\n"
        "| day_no | INT | NO | 일자 번호 |\n"
        "..."
```

---

## 5. Step 4: 청킹 (ChunkRouter)

```python
# chunk_router.py
class ChunkRouter:
    def chunk(doc: ParsedDocument, document_id: str) -> list[ChunkRecord]:
        for element in doc.elements:
            if element.element_type == "table":
                → TableChunkStrategy.chunk(element)
            elif element.element_type == "code":
                → CodeChunkStrategy.chunk(element)
            else:  # "text", "markdown"
                → ParagraphChunkStrategy.chunk(element)
```

### 5.1 ParagraphChunkStrategy (텍스트/마크다운)

```
설정: max_tokens=500 (~1500자), overlap_tokens=80 (~240자)

알고리즘:
    1. 텍스트를 빈 줄(\n\n)로 단락 분리
    2. 각 단락에서 heading 추적:
       "# 제목" → level 1
       "## 소제목" → level 2
       "1.2.3. 항목" → level 3
       → heading_path = "제목 > 소제목 > 항목" (최근 3레벨)
    3. 단락을 누적하며 max_chars(1500) 초과 시 청크 생성
    4. 오버랩: 이전 청크의 마지막 240자를 다음 청크 앞에 포함
    5. 단일 단락이 1500자 초과 시 UTF-8 바이트 경계에서 분할
```

**청크 예시** (마크다운 문서):

```
원본:
# JARVIS 아키텍처
## 검색 파이프라인
FTS와 벡터 검색을 병렬 실행합니다...
(800자)
## 인덱싱
문서를 파싱하고 청킹합니다...
(900자)

결과:
chunk_0: "FTS와 벡터 검색을 병렬 실행합니다..."
         heading_path: "JARVIS 아키텍처 > 검색 파이프라인"
         ~800자

chunk_1: "...병렬 실행합니다(overlap)...\n\n문서를 파싱하고 청킹합니다..."
         heading_path: "JARVIS 아키텍처 > 인덱싱"
         ~240(overlap) + 900 = ~1140자
```

### 5.2 TableChunkStrategy (표 데이터)

```
설정: min_rows_for_split=4

알고리즘:
    1. 요약 청크 생성 (항상):
       "[Sheet1] Table with 14 rows. Columns: Day, 아침, 점심, 저녁"
       heading_path: "table-summary-Sheet1"

    2a. 행 < 4개 → 전체 테이블을 단일 청크:
        "[Sheet1] Day | 아침 | 점심 | 저녁\n1 | 오트밀 | 닭가슴살 | 연어..."
        heading_path: "table-full-Sheet1"

    2b. 행 ≥ 4개 → 각 행을 독립 청크:
        "[Sheet1] Day=1 | 아침=오트밀 | 점심=닭가슴살 | 저녁=연어"
        heading_path: "table-row-Sheet1-0"
        
        "[Sheet1] Day=2 | 아침=그래놀라 | 점심=소고기 | 저녁=두부"
        heading_path: "table-row-Sheet1-1"
        ...
```

**핵심**: 행별 청크에 `header=value` 형식으로 컬럼명을 포함하여, LLM이 전체 테이블 없이도 각 값의 의미를 이해할 수 있습니다.

**검색 시 활용**: `heading_path LIKE 'table-row-%'`로 테이블 행만 필터링, `text LIKE '%Day=3 |%'`로 특정 행 검색

### 5.3 CodeChunkStrategy (소스 코드)

```
설정: max_tokens=500 (~1500자)

알고리즘:
    1차: tree-sitter AST 파싱 (Python, JavaScript, TypeScript)
        → 소스를 AST로 파싱
        → 최상위 정의 노드(class, function, export 등)의 byte 경계 추출
        → 정의 경계에서 분할
        
    2차: regex fallback (Swift, Java, Go 등 tree-sitter 미지원)
        → "class ", "def ", "async def " 패턴으로 줄 단위 분할
        
    병합: 작은 블록(1500자 미만)을 합쳐서 하나의 청크로
    
    초과: 단일 블록이 1500자 초과 시 줄 단위 분할
```

**tree-sitter 지원 언어 및 노드 타입**:

| 언어 | 정의 노드 타입 |
|------|--------------|
| Python | `function_definition`, `class_definition`, `decorated_definition` |
| JavaScript | `function_declaration`, `class_declaration`, `export_statement`, `lexical_declaration` |
| TypeScript | 위 + `interface_declaration`, `type_alias_declaration` |

**청크 예시** (Swift 코드, regex fallback):

```swift
// 원본: ProjectHubNetworkManager.swift (500줄)

// chunk_0: import + 열거형
import Foundation
import Network

enum ConnectionState {
    case disconnected, connecting, connected...
}
// heading_path: "code:swift"
// ~800자

// chunk_1: startHost 함수
func startHost(port: UInt16) {
    let listener = try NWListener(...)
    ...
}
// heading_path: "code:swift"
// ~1200자

// chunk_2: connect 함수
func connect(to host: String, port: UInt16) {
    let connection = NWConnection(...)
    ...
}
// heading_path: "code:swift"
// ~900자
```

---

## 6. Step 5: 즉시 저장 (SQLite)

### 6.1 문서 상태 전이

```
신규 파일 → INDEXING → INDEXED (성공)
                    → FAILED  (실패: 빈 내용, 파서 오류)
                    
기존 파일 (해시 변경):
    기존 chunks 삭제 → 기존 vectors 삭제 → INDEXING → INDEXED/FAILED
    
삭제된 파일 → TOMBSTONED
```

### 6.2 chunks 저장

```python
# index_pipeline.py → _insert_chunks()
for chunk in chunks:
    INSERT INTO chunks (
        chunk_id,        # UUID
        document_id,     # 소속 문서 ID
        byte_start,      # 바이트 오프셋 (시작)
        byte_end,        # 바이트 오프셋 (끝)
        text,            # 청크 텍스트 내용
        chunk_hash,      # SHA256 해시
        lexical_morphs,  # "" (비동기 백필 대기)
        heading_path,    # 섹션 경로 또는 코드 라벨
    )
```

### 6.3 FTS5 자동 인덱싱

```sql
-- chunks_fts는 chunks의 content sync 가상 테이블
-- chunks에 INSERT하면 FTS5 트리거가 자동 발생
-- → text 컬럼으로 영문/숫자 기반 즉시 검색 가능
-- → lexical_morphs는 아직 비어있어 한국어 형태소 검색은 불가
```

**시간선**:
```
t=0s   파일 변경 감지
t=0.1s chunks INSERT + FTS5 트리거 → 영문 검색 가능 ✓
t=0.1s documents status = INDEXED
       ...
t=10m  backfill_morphemes → 한국어 형태소 검색 가능 ✓
t=10m  backfill_embeddings → 벡터 유사도 검색 가능 ✓
```

---

## 7. Step 6: 비동기 백필

### 7.1 형태소 분석 (Kiwi)

```python
# index_pipeline.py → backfill_morphemes()
# 주기: 인덱싱 완료 후 BatchScheduler 또는 health check에서 호출

SELECT chunk_id, text FROM chunks
WHERE lexical_morphs = ''  -- 아직 분석 안 된 것
LIMIT 100                  -- 배치 단위

for chunk_id, text in rows:
    morphs = kiwi.tokenize_for_fts(text[:2000])
    # Kiwi 형태소 분석:
    #   입력: "다이어트 식단표에서 3일차 저녁 메뉴"
    #   POS 필터: NNG(일반명사), NNP(고유명사), VV(동사), VA(형용사)
    #   출력: "다이어트 식단표 일차 저녁 메뉴"
    
    UPDATE chunks SET lexical_morphs = morphs
    WHERE chunk_id = chunk_id
```

**Kiwi POS 태그 필터**:

| 태그 | 의미 | 예시 |
|------|------|------|
| NNG | 일반 명사 | 식단, 메뉴, 구조 |
| NNP | 고유 명사 | JARVIS, ProjectHub |
| VV | 동사 | 검색하다, 찾다 |
| VA | 형용사 | 크다, 작다 |
| MAG | 일반 부사 | 매우, 잘 |

FTS 검색 시 `lexical_morphs` 컬럼에서 형태소 단위로 매칭:
```sql
SELECT * FROM chunks_fts
WHERE chunks_fts MATCH '{text lexical_morphs} : "다이어트" OR {text lexical_morphs} : "식단"'
ORDER BY rank
```

### 7.2 벡터 임베딩 (BGE-M3 + LanceDB)

```python
# index_pipeline.py → backfill_embeddings()
# 주기: 형태소 백필과 동일

SELECT c.chunk_id, c.document_id, c.text FROM chunks c
JOIN documents d ON c.document_id = d.document_id
WHERE c.embedding_ref IS NULL       -- 아직 임베딩 안 된 것
  AND d.indexing_status = 'INDEXED'  -- 성공적으로 인덱싱된 문서만
ORDER BY d.updated_at DESC          -- 최근 문서 우선
LIMIT 32                            -- 배치 단위

# 1. 임베딩 생성
texts = [chunk.text[:2000] for chunk in rows]  # 2000자 제한
embeddings = embedding_runtime.embed(texts)
# BGE-M3: sentence-transformers, CPU
# 출력: list[list[float]], 각 1024차원

# 2. LanceDB 저장
vector_index.add(chunk_ids, document_ids, embeddings)
# LanceDB chunk_embeddings 테이블에 INSERT:
#   chunk_id: "abc-123"
#   document_id: "doc-456"  
#   vector: [0.023, -0.015, 0.042, ...] (1024 floats)

# 3. SQLite 참조 업데이트
UPDATE chunks SET embedding_ref = 'lance:abc-123'
WHERE chunk_id = 'abc-123'
```

**벡터 검색 시 활용**:
```python
# vector_index.py → search()
query_embedding = embed("사용자 질문")  # 1024차원
results = lancedb_table.search(query_embedding).limit(16).to_list()
# ANN (Approximate Nearest Neighbor) 검색
# L2 거리 기반, score = 1.0 - distance
```

---

## 8. 인덱싱 데이터 흐름도

```
Knowledge Base 파일
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    DocumentParser                             │
│                                                              │
│  .md/.txt → 텍스트 읽기 (인코딩 자동 감지)                     │
│  .py      → Python 코드 (language="python")                   │
│  .ts/.js  → JS/TS 코드 (language="typescript"/"javascript")   │
│  .swift   → 일반 코드 (language="")                           │
│  .pdf     → PyMuPDF 블록 추출 + 표 추출                       │
│  .docx    → python-docx 단락 + 표                            │
│  .pptx    → python-pptx 슬라이드별 텍스트 + 표 + 노트          │
│  .xlsx    → openpyxl 시트별 헤더 + 행                         │
│  .hwpx    → hwpx 라이브러리 + XML 직접 파싱                    │
│  .sql     → 구조화 추출 (테이블/컬럼/인덱스/설명)               │
│  기타     → 텍스트 자동 감지 (UTF-8/CP949/EUC-KR)             │
│                                                              │
│  출력: ParsedDocument { elements: DocumentElement[] }         │
│        DocumentElement { element_type, text, metadata }       │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      ChunkRouter                              │
│                                                              │
│  element_type == "table"                                      │
│    → TableChunkStrategy                                       │
│    → 요약 청크 + 행별 청크 (header=value 형식)                  │
│    → heading: table-summary-*, table-row-*                    │
│                                                              │
│  element_type == "code"                                       │
│    → CodeChunkStrategy                                        │
│    → 1차: tree-sitter AST (Python/JS/TS)                      │
│    → 2차: regex fallback (class/def/async def)                │
│    → heading: code:python, code:swift, ...                    │
│                                                              │
│  element_type == "text" / "markdown"                          │
│    → ParagraphChunkStrategy                                   │
│    → 500토큰(1500자), 80토큰(240자) overlap                   │
│    → heading 추적 (# → ## → 1.2.3.)                          │
│                                                              │
│  출력: list[ChunkRecord]                                      │
│        ChunkRecord { chunk_id, text, heading_path, hash }     │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    즉시 저장 (SQLite)                          │
│                                                              │
│  documents: document_id, path, content_hash, status=INDEXED   │
│  chunks: chunk_id, document_id, text, heading_path            │
│  chunks_fts: text + lexical_morphs (FTS5, 자동 트리거)         │
│                                                              │
│  → 영문/숫자 FTS 검색 즉시 가능                                │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              비동기 백필 (10분 주기)                            │
│                                                              │
│  ┌─ backfill_morphemes ────────────────────────────────┐    │
│  │  Kiwi 형태소 분석 (NNG/NNP/VV/VA 추출)               │    │
│  │  batch: 100 chunks                                   │    │
│  │  → chunks.lexical_morphs 업데이트                     │    │
│  │  → 한국어 형태소 FTS 검색 가능                         │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─ backfill_embeddings ───────────────────────────────┐    │
│  │  BGE-M3 임베딩 (1024차원, CPU)                        │    │
│  │  batch: 32 chunks, 최근 문서 우선                      │    │
│  │  → LanceDB chunk_embeddings INSERT                    │    │
│  │  → chunks.embedding_ref = 'lance:chunk_id'            │    │
│  │  → 벡터 유사도 검색 가능                               │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 에러 처리

| 상황 | 처리 |
|------|------|
| 파서 미설치 (pymupdf, python-docx 등) | 빈 문자열 반환, 로그 경고, graceful degradation |
| 파싱 결과 빈 내용 | `indexing_status = FAILED`, ValueError 발생 |
| 인코딩 감지 실패 | UTF-8 errors="replace" fallback |
| 파일 크기 초과 (PDF 500K자) | truncate 후 로그 |
| 텍스트 자동 감지 실패 | `is_indexable() = False`, 인덱싱 건너뜀 |
| LanceDB 저장 실패 | 벡터 없이 FTS만으로 검색 가능 (degraded) |
| Kiwi 형태소 분석 실패 | lexical_morphs 비어있음, 원본 text로 FTS |

---

## 10. 현재 인덱싱 통계

| 항목 | 값 |
|------|-----|
| 총 인덱싱 문서 | ~207개 |
| 총 chunks | ~22,692개 |
| 총 벡터 (BGE-M3) | ~22,692개 |
| 벡터 차원 | 1024 |
| 평균 청크 크기 | ~500자 |
| 지원 파일 형식 | 60+ 확장자 |
| 바이너리 파서 | PDF, DOCX, PPTX, XLSX, HWPX, HWP |
| AST 파서 | Python, JavaScript, TypeScript (tree-sitter) |
