# 2026-03-19 Menu Bar UI Bridge Design

## 목적

기술문서 `TASK-E93DF600.md`의 Interface Layer 요구사항 중
`menu bar UI`, `status display`, `citation display`, `approval panel`
을 실제 구현 가능한 최소 단위로 분해한다.

이번 단계의 목표는 전체 macOS 앱 완성이 아니라,
`SwiftUI 메뉴바 셸 + Python JSON bridge`를 먼저 세우는 것이다.

## 문서 기준

- 기본 인터페이스는 `CLI REPL, then menu bar UI`
- 메뉴바 UI는 `query`, `response`, `source display`, `execution approval`
  를 담당한다.
- 구현 환경은 `Local development Python, minimal SwiftUI UI, MLX runtime`

## 결정

1. Python 코어는 유지한다.
2. macOS UI는 별도 SwiftUI 프로세스로 둔다.
3. 1차 연결은 `stdin/stdout line-delimited JSON` 장기 실행 브리지로 한다.
4. 메뉴바 1차 범위는 `text query`, `response`, `citations`, `runtime status`다.
5. `approval panel`은 현재 메뉴바 UI에 연결한다.
6. `live PTT loop`는 동일 UI 위에 연결한다.

## 브리지 계약

Python 모듈:

- `jarvis.cli.menu_bridge`

입력:

- `--query`
- `--model` optional

출력 JSON:

```json
{
  "query": "pipeline.py 설명해줘",
  "response": "답변 본문",
  "has_evidence": true,
  "citations": [
    {
      "label": "[1]",
      "source_path": "/path/to/file.py",
      "source_type": "code",
      "quote": "def run_pipeline(): ...",
      "state": "VALID",
      "relevance_score": 0.93
    }
  ],
  "status": {
    "mode": "normal",
    "safe_mode": false,
    "degraded_mode": false,
    "generation_blocked": false,
    "write_blocked": false,
    "rebuild_index_required": false
  }
}
```

## SwiftUI 구조

경로:

- `macos/JarvisMenuBar/Package.swift`
- `macos/JarvisMenuBar/Sources/JarvisMenuBarApp.swift`
- `macos/JarvisMenuBar/Sources/JarvisBridge.swift`
- `macos/JarvisMenuBar/Sources/MenuModels.swift`

구성:

1. `MenuBarExtra`로 메뉴바 창 생성
2. 상단 질의 입력창 + `Ask` 버튼
3. 본문 답변 영역
4. citation 리스트
5. safe/degraded/write-block 상태 배지
6. 승인형 export panel
7. PTT once 버튼
8. live loop 시작/중지 버튼 + 상태 표시

## 후속 작업

1. export 대상을 UI에서 더 정교하게 제어
   - 저장 위치 preset
   - 형식 선택(txt/md)
   - overwrite warning
2. live loop를 백그라운드 친화적으로 조정
   - 성공 후 짧은 cooldown
   - 오류 후 긴 backoff
   - 연속 오류 3회 시 자동 중지
3. bridge stderr / optional dependency 경고를 더 정리
4. health 상태를 더 세분화
   - failed checks 목록
   - vector search / knowledge base 상태
   - 항목별 detail row
