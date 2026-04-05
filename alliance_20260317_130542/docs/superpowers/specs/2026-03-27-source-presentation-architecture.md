# Source Presentation Architecture

Date: 2026-03-27
Owner: Codex
Status: Draft

## Goal

검색 답변이 문장으로 끝나더라도, 사용자가 실제 근거를 바로 볼 수 있도록
문서, 표, 그림, 웹 페이지 같은 원본 소스를 frontend에서 열고 미리보기할 수 있게 한다.

핵심 원칙은 다음과 같다.

- retrieval은 `무엇이 근거인가`를 결정한다.
- source presentation은 `그 근거를 어떻게 보여줄 것인가`를 담당한다.
- answer text와 source presentation은 분리하되, 같은 evidence를 기준으로 연결된다.

## Problem

현재는 다음과 같은 한계가 있다.

- 답변 본문은 좋아졌지만, 사용자가 원문 구조를 직접 확인할 수 없다.
- `파일상에는 다음과 같은 구조로 저장된다.` 같은 응답 이후 실제 구조 본문, 표, 도식, 웹 페이지를 이어서 보이기 어렵다.
- citation은 있으나, frontend가 source artifact를 직접 렌더링하거나 위치 이동하는 계약은 약하다.

## Phase 1 Scope

1. 문서/파일 열기
2. citation preview 노출
3. heading_path 기반 위치 힌트 표시

이 단계에서는 "정확한 페이지 점프"를 모든 형식에 대해 보장하지 않는다.

## Target UX

사용자가 답변을 받으면 frontend는 아래 중 하나를 제공한다.

- `원문 열기`
- `해당 섹션 보기`
- `표 보기`
- `웹 열기`

예시:

- HWP/HWPX/PDF
  - 파일 열기
  - heading path / quote preview 표시
- XLSX/CSV
  - 관련 row/column preview 표시
- 코드 파일
  - 클래스/함수 주변 snippet 표시
- 웹 페이지
  - URL 열기
  - title/snippet 표시

## Contract Extension

현재 citation 중심 payload를 아래 방향으로 확장한다.

```json
{
  "source_presentation": {
    "kind": "document_section",
    "source_path": "/abs/path/file.hwp",
    "heading_path": "그리기 개체 자료 구조 > 기본 구조",
    "quote": "그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에...",
    "open_target": {
      "kind": "file"
    },
    "preview": {
      "kind": "text",
      "text": "그리기 개체는 여러 개의 개체를..."
    }
  }
}
```

### Presentation kinds

- `document_section`
- `table_row`
- `code_symbol`
- `web_page`
- `image_or_figure`

## Backend Responsibilities

- top evidence를 기준으로 presentation payload 구성
- `source_path`, `heading_path`, `quote`, `preview` 정규화
- 형식별 최소 미리보기 생성
- frontend가 바로 그릴 수 있는 구조 제공

### HWP/HWPX/PDF

- `heading_path`와 `quote`를 우선 제공
- 파일 열기 지원
- page metadata가 있을 때만 page jump 제공

### Table

- row/field를 자연어 답변과 별도로 구조화해 제공
- 예:
  - `row_key=Day=11`
  - `fields=["Breakfast", "Dinner"]`
  - `preview_rows=[...]`

### Web

- URL
- title
- snippet

## Frontend Responsibilities

- source presentation panel 렌더링
- 파일 열기 / 링크 열기
- quote preview / section title 표시
- answer text와 source artifact를 명확히 분리

## Recommended Implementation Order

1. `ServiceAskResponse`에 `source_presentation` 추가
2. top citation 기준 backend payload 생성
3. Swift Guide panel에 `원문 열기` / `미리보기` 추가
4. 문서 형식별 preview 확장
5. 이후 page/anchor jump 검토

## Out of Scope

- HWP 내부 정확 위치 점프 보장
- 모든 포맷의 완전한 embedded renderer
- 생성형 멀티모달 설명 UI

## Immediate Next Step

다음 구현 단계는 아래가 적절하다.

1. backend가 `top evidence -> source_presentation` payload 생성
2. Swift Guide panel에서 `원문 열기` 버튼과 `heading_path/quote preview` 표시

