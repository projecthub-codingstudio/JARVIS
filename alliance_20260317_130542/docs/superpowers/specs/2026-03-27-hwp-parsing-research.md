# HWP 파싱 연구 검토 리포트

Date: 2026-03-27
Purpose: JARVIS 프로젝트의 HWP 파싱 현황 분석 및 개선 방안 연구

---

## 1. 현재 JARVIS 구현 상태

### 1.1 파싱 파이프라인

```
.hwp  -> hwp5proc xml (subprocess, 120초 타임아웃) -> lxml XML 파싱 -> DocumentElement[]
.hwpx -> python-hwpx (HwpxPackage + TextExtractor) + ZIP XML 직접 파싱 -> DocumentElement[]
```

### 1.2 사용 중인 라이브러리

| 라이브러리 | 버전 | 라이선스 | 용도 |
|-----------|------|---------|------|
| pyhwp | 0.1b15 | AGPL-3.0 | HWP 바이너리 -> XML 변환 (hwp5proc subprocess) |
| python-hwpx | 2.8.3 | MIT | HWPX 텍스트/테이블 추출 |
| olefile | 0.47 | BSD-2 | OLE2 저수준 접근 (pyhwp 내부 의존) |
| lxml | 5.2+ | BSD | XML 파싱 (2026-03-27 명시 추가) |

### 1.3 파싱 호출 그래프

```
DocumentParser.parse_structured(path)
  |-- detect_type() -> "hwp"
  |     +-- _parse_hwp_structured(path)
  |           +-- subprocess: hwp5proc xml <path>     [120초 타임아웃]
  |                 -> stdout bytes -> _parse_hwp_structured_xml_bytes(bytes)
  |                       |-- lxml.etree.fromstring()
  |                       |-- Pass 1: 테이블 내부 요소 집합 구축
  |                       |-- Pass 2: text_buffer 수집 + TableBody 추출
  |                       |     |-- _flush_text() -> _build_hwp_text_elements()
  |                       |     |       -> DocumentElement(type="text", metadata={heading_path?})
  |                       |     +-- _extract_hwp_table_rows(TableBody)
  |                       |           + _get_table_caption(TableBody)
  |                       |           -> DocumentElement(type="table", metadata={headers,rows,sheet_name})
  |                       +-- returns list[DocumentElement]
  |           [fallback: hwp5proc 부재 -> []]
  |     [fallback: structured 빈 결과 -> parse() -> _parse_hwp_xml() 또는 hwp5txt]
  |
  +-- detect_type() -> "hwpx"
        +-- _parse_hwpx_structured(path)
              |-- HwpxPackage.open() + TextExtractor.extract_text()
              |     -> DocumentElement(type="text")
              |-- [fallback: _parse_hwpx_fallback() -> ZIP+XML 텍스트 연결]
              +-- _extract_hwpx_tables(path)
                    |-- zipfile.ZipFile -> Contents/*.xml
                    |-- ElementTree -> {hp:}tbl -> hp:tr -> hp:tc -> hp:t
                    +-- -> list[DocumentElement(type="table")]
```

### 1.4 DocumentElement 출력 구조

```python
@dataclass(frozen=True)
class DocumentElement:
    element_type: str   # "text", "table", "code"
    text: str           # human-readable representation
    metadata: dict      # type-specific; tables: headers, rows, sheet_name
```

HWP 테이블의 metadata:
- headers: tuple[str, ...] -- 첫 번째 행
- rows: tuple[tuple[str, ...], ...] -- 이후 행들
- sheet_name: TableCaption 텍스트 (예: "표 76 그리기 개체 공통 속성") 또는 "HWP Table N" 폴백

HWPX 테이블의 metadata:
- sheet_name: 인접 caption/표 제목 텍스트 또는 "Table N" 폴백

---

## 2. 발견된 문제점

### 문제 1: 헤딩/섹션 계층 구조 부재 (가장 심각)

HWP 파싱에서 단락 스타일(outline level)을 전혀 읽지 않는다. 유일한 헤딩 감지는 6개 하드코딩 문자열:

```python
_HWP_SUBHEADINGS = ("기본 구조", "저장 구조", "공통 속성", "개체 속성", "텍스트 정보", "텍스트 속성")
```

이것은 한글문서파일형식 사양서 1개 문서에만 작동하는 도메인 특화 해킹이다. 다른 HWP 문서에서는 모든 텍스트가 평탄한 단락으로 처리된다.

영향: RAG 합의안의 "document -> section -> chunk 계층 검색"이 HWP 문서에서 불가능.

### 문제 2: 병합 셀 미처리

HWP 테이블은 rowspan/colspan을 빈번하게 사용한다. 현재 코드는 TableRow 하위의 TableCell 자식만 순회하므로, 병합으로 생략된 셀이 있으면 행 길이가 헤더와 불일치한다.

```
헤더: [이름, 타입, 크기, 설명]  (4열)
행:   [필드A, 타입B]           (2열, 병합 셀 누락)
-> "크기=", "설명=" 매핑이 사라짐
```

TableChunkStrategy는 headers[i] fallback으로 "col{i}"를 사용하므로 크래시는 않지만, 헤더-값 매핑이 조용히 잘못된다.

### 문제 3: lxml이 pyproject.toml에 미선언

원래는 `_parse_hwp_structured_xml_bytes()`가 `lxml.etree`를 필수로 사용하지만, pyproject.toml에 의존성 선언이 없었다. 2026-03-27 현재 `lxml>=5.2`를 명시 추가했고, 이 이슈는 코드 레벨에서 해소됐다.

### 문제 4: HWPX 테이블 캡션 미추출

원래 HWP 바이너리 경로는 TableCaption 요소에서 캡션을 추출하지만("표 76 그리기 개체 공통 속성"), HWPX 경로는 "Table N" 제네릭 레이블만 생성했다. 2026-03-27 현재는 인접 caption/표 제목 문단을 table `sheet_name`으로 승격하는 parser 보강이 들어갔다. 다만 실제 HWPX 산출물 전체에서 충분한지는 추가 샘플 검증이 필요하다.

### 문제 5: 죽은 코드 -- _parse_hwpx() flat 경로

_parse_hwpx()가 from hwpx import HWPXFile을 임포트하지만, 이 클래스는 python-hwpx 패키지에 존재하지 않는다 (실제 API: HwpxPackage, TextExtractor, HwpxDocument). 매번 ImportError/AttributeError로 폴백된다.

프로덕션에서는 parse_structured()만 호출되어 무해하지만, parse() 직접 호출 시 항상 폴백 경로로 진입한다.

### 문제 6: 이미지/그리기 개체 완전 손실

<그림> 플레이스홀더가 제거되고 그리기 개체는 무시된다. 캡션만 남은 단락이 빈 청크를 생성할 수 있다 (if paragraph_text: 가드로 크래시는 방지).

그리기 개체(ShapeComponent)는 HWP 사양서에서 핵심 콘텐츠이나 완전히 손실된다.

### 문제 7: HWP 문서 크기 제한 없음

PDF 파서는 500,000자 상한이 있으나 HWP 파서에는 없다. 수천 페이지 사양서에서 무제한 청크 생성 가능.

### 문제 8: 단일 행 테이블 무조건 삭제

len(rows_data) < 2 조건으로 헤더만 있는 테이블을 건너뛴다. 정의 테이블이나 메타데이터 테이블처럼 유효한 1행 테이블도 손실된다.

---

## 3. HWP 포맷 구조 분석

### 3.1 HWP 바이너리 (.hwp) -- OLE2 Compound Document

컨테이너: Microsoft OLE2 Compound File Binary Format (CFB)

주요 스트림:

| 스트림 | 용도 | 압축 | 암호화 가능 |
|--------|------|------|-----------|
| FileHeader | 256바이트 고정 헤더: 시그니처, 버전, 플래그 | X | X |
| DocInfo | 공유 메타데이터: 폰트, 문자/단락 스타일, ID 매핑 | zlib | O |
| BodyText/Section0, 1, ... | 실제 문서 내용 (단락, 테이블, 그리기) | zlib | O |
| BinData/BIN0001.jpg, ... | 임베디드 바이너리 리소스 (이미지, OLE) | zlib | O |
| Scripts/DefaultJScript | 매크로/스크립트 | zlib | O |
| PrvText | 미리보기 텍스트 (첫 페이지, UTF-16LE) | X | X |
| PrvImage | 미리보기 PNG 이미지 | X | X |

레코드 구조: DocInfo, BodyText 스트림 내부는 32비트 헤더 레코드 시퀀스.
- Tag ID (10비트): 레코드 타입 (HWPTAG_PARA_TEXT = 0x042 등)
- Level (10비트): 계층 깊이 (부모-자식 그룹핑)
- Size (12비트): 페이로드 길이 (4095이면 추가 DWORD)

인코딩: HWP 5.x 내부 UTF-16LE. pyhwp의 hwp5proc xml 출력은 UTF-8 XML.

압축: raw DEFLATE (zlib wbits=-15, 헤더 없음).

### 3.2 HWPX (.hwpx) -- OWPML XML 기반

컨테이너: ZIP 아카이브. KS X 6101 (OWPML) 표준.

```
mimetype                          (application/hwp+zip)
META-INF/manifest.xml             (패키지 매니페스트)
Contents/content.hpf              (콘텐츠 매니페스트)
Contents/header.xml               (문서 수준 설정)
Contents/section0.xml             (섹션 내용)
BinData/BIN0001.jpg               (임베디드 리소스)
```

XML 네임스페이스:
- hp = http://www.hancom.co.kr/hwpml/2011/paragraph (단락, 런, 텍스트, 테이블)
- hs = http://www.hancom.co.kr/hwpml/2011/section (섹션 구조)
- hc = http://www.hancom.co.kr/hwpml/2011/common

주요 요소: hp:p (단락), hp:run (텍스트 런), hp:t (텍스트), hp:tbl (테이블), hp:tr/hp:tc (행/셀), hp:pic (이미지), hp:ctrl (컨트롤 객체)

### 3.3 HWP vs HWPX 비교

| 항목 | HWP (바이너리) | HWPX (XML) |
|------|--------------|-----------|
| 컨테이너 | OLE2 Compound Document | ZIP 아카이브 |
| 내부 포맷 | 바이너리 레코드 (zlib 압축) | XML 파일 |
| 인코딩 | UTF-16LE (내부) | UTF-8 |
| 파싱 난이도 | 높음 | 낮음 |
| 표준 | 독점적 (한컴) | KS X 6101 (OWPML 국가표준) |
| 도구 지원 | 제한적 (pyhwp) | 양호 (모든 XML 파서) |
| 채택 현황 | 레거시, 여전히 다수 | 증가 중, 정부 권장 |

HWPX는 한컴오피스 2014부터 지원. 한국 정부가 개방형 포맷으로 HWPX를 권장하고 있으나, 기존 문서 아카이브에서 HWP가 압도적.

---

## 4. 추출 가능 콘텐츠 현황

| 콘텐츠 유형 | HWP 바이너리 | HWPX |
|---|---|---|
| 본문 텍스트 단락 | O | O |
| 테이블 (헤더 + 행) | O (캡션 포함) | O (캡션 미포함) |
| 테이블 캡션 | O (TableCaption 요소) | X |
| 헤딩/섹션 계층 | 휴리스틱만 (6개 문자열) | X |
| 이미지/그림 | X (삭제) | X |
| 머리글/바닥글 | X | X |
| 각주/미주 | X | X |
| OLE 객체 | X | X |
| 주석/코멘트 | X | X |
| 수식 | X | X |
| 다단 레이아웃 | 선형화 | 선형화 |
| 병합 셀 | X (미처리) | X (미처리) |
| 단락 스타일 (outline level) | X (미읽음) | X (미읽음) |

---

## 4.1 2026-03-27 반영 현황

이번 세션에서 바로 반영된 항목:

- `pyproject.toml`에 `lxml>=5.2` 명시
- HWP parser 테스트 helper 추가
  - `_parse_hwp_structured_xml_bytes(...)`
- HWP inline heading 승격 helper 추가
  - `_build_hwp_text_elements(...)`
- HWP recent heading context 전파 추가
  - 같은 section의 후속 설명 문단이 직전 heading을 상속
- HWPX table caption 추출 보강
  - 인접 caption/표 제목 문단을 `sheet_name`으로 사용
- parser 회귀 테스트 추가/보강
  - `test_hwp_structured.py`
  - `test_hwpx_structured.py`

이 변경은 parser 레벨 반영이며, 실제 검색 품질 변화는 재인덱싱 후에만 반영된다.

추가 확인:

- `hwp5proc`는 실제 설치되어 있고 live 환경에서 정상 실행된다
- live HWP 재인덱싱 후 `그리기 개체 자료 구조 > 기본 구조` chunk가 실제 DB에 반영됨
- 단, SQLite 재인덱싱 뒤에는 stale LanceDB vector 정리가 함께 수행되어야 retrieval baseline이 유지된다

---

## 5. Python HWP 파싱 라이브러리 현황

### 5.1 현재 사용 중

| 라이브러리 | HWP | HWPX | Stars | 라이선스 | 최근 활동 | 비고 |
|-----------|-----|------|-------|---------|----------|------|
| pyhwp | v5 | X | ~200 | AGPL-3.0 | 2023 | 가장 성숙한 Python HWP 파서 |
| python-hwpx | X | O | 41 | MIT | 2026.03 | 최고 HWPX 라이브러리, 활발 유지보수 |
| olefile | (저수준) | X | - | BSD-2 | - | pyhwp 내부 의존 |

### 5.2 대안 Python 라이브러리

| 라이브러리 | HWP | HWPX | 라이선스 | 특징 |
|-----------|-----|------|---------|------|
| hwp-extract (Volexity) | v5 | X | BSD-3 | 보안/포렌식, 암호화 HWP 지원 |
| gethwp | O | O | MIT | 경량, 최소 기능 |
| kreuzberg | O | O | - | Rust 코어, 91+ 포맷, 베타 (2026.03 활성) |
| pyhwpx | X | X | - | win32com 래퍼, Windows 전용 (부적합) |
| hwpapi | X | X | - | win32com 래퍼, Windows 전용 (부적합) |

### 5.3 Rust 라이브러리 (주목)

| 프로젝트 | Stars | 라이선스 | HWP | HWPX | 특징 |
|---------|-------|---------|-----|------|------|
| unhwp | 5 | MIT | O | O | Markdown/JSON 출력, C-ABI FFI, macOS ARM 바이너리 |
| openhwp | 75 | MIT | Read | R/W | KS X 6101:2024 기반 |
| hwp-rs | ~100 | - | O | - | 저수준, Python 바인딩 (libhwp) |
| hwpers | - | - | O | - | 레이아웃 렌더링, SVG 출력 |

---

## 6. 대안 접근법 평가

| 방법 | 장점 | 단점 | JARVIS 적합도 |
|------|------|------|-------------|
| pyhwp + python-hwpx (현재) | 검증됨, 순수 Python | 헤딩/병합셀 미지원, AGPL | 현재 최선 |
| unhwp (Rust CLI) | 빠름, JSON 구조, 헤딩/이미지 보존, M1 바이너리 | 신생 프로젝트 (5 stars) | 유망 -- 평가 필요 |
| LibreOffice headless | 복잡 레이아웃 | macOS M1에서 HWP 변환 실패 보고, 800MB+ | 낮음 |
| Apache Tika | 다포맷 | HWP 미지원 | 불가 |
| Cloud API | 높은 정확도 | 오프라인 불가, 프라이버시 위반 | 불가 |
| kreuzberg | Rust 코어, 다포맷 | 베타, HWP 지원 깊이 미확인 | 모니터링 |

---

## 7. unhwp 상세 평가

현재 파싱 스택의 한계를 가장 직접적으로 보완할 수 있는 도구.

### 장점
- HWP + HWPX 모두 지원 (pyhwp는 HWP만, python-hwpx는 HWPX만)
- JSON 구조 출력 -- 헤딩, 스타일, 테이블, 이미지 메타데이터 포함
- Markdown 출력 -- LLM 친화적 클린업 모드
- macOS Apple Silicon 바이너리 -- M1 Max에서 네이티브 실행
- MIT 라이선스 -- pyhwp의 AGPL 대비 자유로움
- C-ABI FFI -- Python에서 ctypes/cffi로 직접 호출 가능

### 단점
- 신생 프로젝트 (81 커밋, 5 stars)
- 프로덕션 안정성 미검증
- 커뮤니티 지원 제한

### 적용 전략
- pyhwp를 주 경로로 유지
- unhwp를 보조/폴백 경로로 평가
- JSON 출력의 헤딩 계층 정보가 정확하면 점진적 전환 검토

GitHub: https://github.com/iyulab/unhwp

---

## 8. 권장 개선 방안

### Priority 1: 즉시 수정 (1-2일)

| # | 작업 | 근거 |
|---|------|------|
| 1 | lxml을 pyproject.toml에 명시적 의존성 추가 | 미설치 시 HWP 전체 파싱 무음 실패 방지 |
| 2 | HWPX 테이블 캡션 추출 구현 | HWP 바이너리와 동등한 테이블 식별 |
| 3 | 죽은 코드 _parse_hwpx() 정리 | 존재하지 않는 API 참조 제거 |
| 4 | HWP 문서 크기 제한 추가 (500,000자) | PDF와 동등한 상한 적용 |

### Priority 2: 구조 개선 (3-5일)

| # | 작업 | 근거 |
|---|------|------|
| 5 | HWP 헤딩 계층 추출 -- DocInfo 스트림에서 단락 스타일 ID -> outline level 매핑 | RAG 계층 검색의 전제 조건 |
| 6 | 병합 셀 처리 -- TableCell 속성에서 colspan/rowspan 읽고 빈 셀 보정 | 테이블 검색 정확도 핵심 |
| 7 | HWPX 헤딩 추출 -- 단락 스타일 참조에서 outline level 읽기 | HWPX 문서에서도 섹션 검색 가능 |

### Priority 3: 파서 강화 (1-2주)

| # | 작업 | 근거 |
|---|------|------|
| 8 | unhwp 평가 -- Rust CLI를 보조 파싱 경로로 테스트 | JSON 구조 출력, 헤딩/이미지 보존, MIT 라이선스 |
| 9 | 이미지/그리기 개체 메타데이터 보존 | 최소한 "[이미지: 캡션텍스트]" 플레이스홀더 유지 |
| 10 | 중첩 테이블 지원 | 정부 양식에서 빈번 |

### Priority 4: 향후 검토

| # | 작업 | 조건 |
|---|------|------|
| 11 | kreuzberg 프레임워크 평가 | Rust 코어 성숙 시 (현재 베타) |
| 12 | HWP 3.x 지원 | 레거시 아카이브 필요 시 |
| 13 | 암호화 HWP 지원 (hwp-extract) | 보안 문서 처리 필요 시 |

---

## 9. RAG 합의안과의 연관

RAG 검색 최종 합의안(2026-03-27-retrieval-final-consensus.md)에서 확정된 원칙 4 "장문 문서는 계층적 검색을 목표"가 HWP 파싱에 직접적 영향을 미친다:

- document -> section -> chunk 3단계 검색을 위해서는 파서가 헤딩 계층을 출력해야 한다
- 현재 HWP 파서는 헤딩을 추출하지 않으므로, Priority 2 (#5, #7)가 RAG 개선의 전제 조건
- Section-aware DocumentStrategy가 구현되어도, 파서가 섹션 정보를 제공하지 않으면 무의미

따라서 HWP 헤딩 추출은 RAG Step 4 (DocumentRetriever 분리)와 병렬로 진행되어야 한다.

---

## 10. 핵심 소스 파일

| 파일 | 역할 |
|------|------|
| src/jarvis/indexing/parsers.py | 모든 HWP/HWPX 파싱 로직 |
| src/jarvis/contracts/models.py | DocumentElement, ParsedDocument 데이터 계약 |
| src/jarvis/indexing/strategies/table.py | TableChunkStrategy (행별 청킹) |
| src/jarvis/indexing/chunk_router.py | ChunkRouter (element_type별 디스패치) |
| src/jarvis/indexing/index_pipeline.py | IndexPipeline (파싱 -> 청킹 -> 임베딩 -> 저장) |
| tests/indexing/test_hwp_structured.py | HWP 바이너리 구조화 파싱 테스트 |
| tests/indexing/test_hwpx_structured.py | HWPX 구조화 파싱 테스트 |

---

## 11. 참고 자료

### 라이브러리
- pyhwp: https://github.com/mete0r/pyhwp
- python-hwpx: https://github.com/airmang/python-hwpx
- unhwp: https://github.com/iyulab/unhwp
- openhwp: https://github.com/openhwp/openhwp
- hwp-rs: https://github.com/hahnlee/hwp-rs
- hwpers: https://github.com/Indosaram/hwpers
- hwp-extract: https://github.com/volexity/hwp-extract
- kreuzberg: https://github.com/kreuzberg-dev/kreuzberg
- H2Orestart: https://github.com/ebandal/H2Orestart

### 포맷 사양
- Hancom Tech Blog HWP 포맷 구조: https://tech.hancom.com
- KS X 6101 (OWPML): 한국 국가표준 개방형 워드프로세서 마크업 언어
- Archive Team HWP: http://justsolve.archiveteam.org/wiki/HWP
- ClamAV HWP 분석: https://blog.clamav.net/2016/03/clamav-0991-hangul-word-processor-hwp.html
