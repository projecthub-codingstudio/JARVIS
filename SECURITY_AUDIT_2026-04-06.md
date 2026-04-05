# JARVIS 전체 보안 점검 보고서

**점검일**: 2026-04-06
**범위**: 백엔드 API (FastAPI) · 프론트엔드 (React/TypeScript) · 데이터 프라이버시
**점검 방법**: 3개 영역 병렬 코드 감사 + 동적 검증

---

## 🔴 Critical (즉시 수정 필요)

### C-1. Firebase API 키가 저장소에 커밋됨

**파일**: `ProjectHub-terminal-architect/firebase-applet-config.json`

```json
{
  "projectId": "gen-lang-client-0554693878",
  "apiKey": "AIzaSyDqrPLuO6U_OeEr7wDtJkHn7hVJQxeN8As",
  ...
}
```

이전 Firebase 통합의 잔재. 현재 코드베이스 어디에서도 import하지 않지만 **public repo에 평문으로 노출**되어 있음. Firebase Web API Key는 Firestore security rules로 보호되지만 해당 프로젝트의 접근 권한이 느슨하다면 실제 위험.

**조치**:
```bash
git rm --cached ProjectHub-terminal-architect/firebase-applet-config.json
echo "firebase-*.json" >> .gitignore
# Google Cloud Console에서 API 키 회전
```

### C-2. 백엔드 서버가 기본값 `0.0.0.0`에 바인딩됨

**파일**: `alliance_20260317_130542/src/jarvis/web_api.py:690`

```python
default="0.0.0.0"
```

같은 Wi-Fi 또는 LAN의 **모든 기기**가 인증 없이 접근 가능. `/api/file`로 전체 파일 시스템, `/api/ask`로 LLM, `/api/learned-patterns`로 쿼리 이력 열람 가능.

**조치**: 기본값을 `127.0.0.1`로 변경. LAN 노출이 필요한 경우에만 명시적으로 `--host 0.0.0.0` 지정하도록.

### C-3. `/api/file/extracted` 경로 검증 누락

**파일**: `web_api.py:461-465`

절대 경로 입력 시 `relative_to(kb_root)` 가드가 실행되지 않음 → knowledge_base 외부 파일의 인덱싱 여부를 oracle로 탐지 가능 (`/etc/passwd`, `/Users/xxx/.ssh/` 등).

**조치**: `/api/file`, `/api/browse`와 동일한 경로 검증 추가.

---

## 🟠 High (다음 스프린트 수정)

### H-1. 서버가 query 길이 제한 없음 (DoS)
- **파일**: `web_api.py:52-53` (`AskRequest` model)
- 10MB 쿼리로 OOM 유발 가능
- **조치**: `Field(max_length=16_000)` 추가

### H-2. WebSocket 예외 메시지가 클라이언트에 노출
- **파일**: `web_api.py:667-670`
- `str(e)`를 그대로 전송 → 내부 경로, 스택트레이스 누출
- **조치**: 내부 로깅만, 클라이언트엔 `"Internal server error"`

### H-3. `/api/ask/vision` MIME 검증 미흡
- **파일**: `web_api.py:407-417`
- 확장자만 체크, 실제 magic bytes 검증 없음 → `.png` 이름으로 임의 바이너리 업로드 가능
- **조치**: `python-magic` 또는 `imghdr`로 magic bytes 검증

### H-4. `DocxRenderer` XSS 미방지
- **파일**: `DocxRenderer.tsx:24-27`
- `docx-preview` 출력을 DOMPurify 거치지 않고 DOM에 삽입
- **조치**: `renderAsync` 완료 후 `containerRef.current.innerHTML`에 DOMPurify 적용

### H-5. `WebRenderer` iframe `allow-popups` 허용
- **파일**: `WebRenderer.tsx:26`
- Tab-napping 공격 가능
- **조치**: `allow-popups` 제거, `referrerpolicy="no-referrer"` 추가

### H-6. Vite 개발 서버 `0.0.0.0` 바인딩
- **파일**: `package.json:7` — `"dev": "vite --port=3000 --host=0.0.0.0"`
- LAN 공유 카페/사무실에서 노출
- **조치**: `--host=127.0.0.1`로 변경

### H-7. Google Fonts CDN → 개인정보 원칙 위배
- **파일**: `src/index.css:1`
- 매 페이지 로드마다 IP를 Google에 전송 — "privacy-first, offline-capable" 원칙 정면 위배
- **조치**: `@fontsource/inter` + `@fontsource/jetbrains-mono`로 로컬 번들

### H-8. 액션 맵 `launch_target` 명령 주입 위험
- **파일**: `core/action_resolver.py:150-158`
- `subprocess.run(["open", target.target])` — `/api/action-maps` POST로 임의 launch_target 등록 가능
- **조치**: URL scheme 화이트리스트, 경로 검증

---

## 🟡 Medium (점진적 개선)

### M-1. `PptxRenderer` / `XlsxRenderer` CSS exfiltration 가능
- DOMPurify 기본 설정은 `<style url()>` 차단하지 않음
- **조치**: `FORBID_ATTR: ['style']`, `FORBID_TAGS: ['base']` 추가

### M-2. `/api/health` 절대 경로 누출
- `knowledge_base_path: "/Users/xxx/..."` 반환 → 사용자명 노출
- **조치**: boolean으로 변환하거나 basename만 노출

### M-3. `/api/learned-patterns` citation_paths 절대 경로 노출
- **조치**: kb_root 기준 상대 경로로 변환

### M-4. `/api/file/extracted` limit 파라미터 무제한
- **조치**: `Query(default=200, ge=1, le=1000)`

### M-5. 보안 헤더 부재
- `X-Content-Type-Options`, `X-Frame-Options`, `CSP` 미설정
- **조치**: SecurityHeadersMiddleware 추가

### M-6. TypeScript strict mode 비활성
- `tsconfig.json`에 `"strict": true` 없음
- **조치**: null-safety 활성화

### M-7. CSRF 보호 없음
- LAN 노출 시 cross-origin POST 가능
- **조치**: 백엔드에서 `Origin` 헤더 검증 또는 CSRF 토큰

### M-8. 이미지 업로드 클라이언트 검증 미흡
- **파일**: `TerminalWorkspace.tsx:1313`
- `file.type.startsWith('image/')` 체크 누락
- **조치**: onChange 핸들러에 MIME 검증 추가

---

## 🔵 Low / Informational

### L-1. HuggingFace 오프라인 모드 미설정
- `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` 미설정 → 첫 호출 시 조용히 네트워크 체크
- **조치**: 시작 시 환경변수 설정 + `local_files_only=True`

### L-2. 쿼리 이력 무제한 보관
- `conversation_turns`, `session_events`, `task_logs` — TTL 없음
- **조치**: "모든 데이터 삭제" 워크플로우 추가

### L-3. 로그 로테이션 없음
- `.pids/backend.log` 무제한 증가
- **조치**: `RotatingFileHandler` (5MB × 3 backups)

### L-4. `xlsx@0.18.5` CVE-2023-30533 (prototype pollution)
- **조치**: `@e965/xlsx` 포크 또는 `exceljs` 고려

### L-5. 프롬프트 인젝션 위험 (중간)
- knowledge_base에 악성 문서 배치 시 "Ignore all previous instructions..." 공격 가능
- **조치**: evidence 블록 주위에 anti-injection framing 추가

### L-6. 레거시 `terminal-architect/` 디렉토리 Gemini API 키 placeholder
- **조치**: 디렉토리 제거 또는 archive

### L-7. 외부 API 호출 (사용자 트리거, 설계상 의도됨)
- `wttr.in` (날씨), `nominatim.openstreetmap.org` (지오코딩), `api.duckduckgo.com` (웹 검색)
- 사용자가 해당 기능을 명시적으로 호출해야 전송 → **설계상 의도**
- **조치**: README에 명시적 disclosure 추가 권장

---

## ✅ Passes (명시적 확인)

- **경로 traversal (`/api/browse`, `/api/file`)**: `relative_to(kb_root.resolve())` 올바르게 적용
- **SQL 인젝션**: 모든 SQLite 쿼리 parameterized
- **Temp 파일 정리**: `/api/ask/vision`의 `try/finally` 정상 동작
- **API 키/시크릿**: 활성 코드베이스에 하드코드된 시크릿 없음 (firebase-applet-config.json 제외)
- **XSS MarkdownRenderer**: `rehype-raw` 미사용, react-markdown이 React 엘리먼트로 렌더링 → 안전
- **XSS HtmlRenderer**: `sandbox=""` + DOMPurify 정상 동작
- **외부 스크립트**: index.html에 CDN `<script>` 태그 없음 (fonts.googleapis.com CSS 제외)
- **localStorage/sessionStorage**: 사용 없음, sessionId는 Zustand in-memory
- **URL 인코딩**: `api-client.ts`의 모든 동적 경로 파라미터 `encodeURIComponent` 처리
- **WebSocket 세션 격리**: session_id가 파일 경로나 SQL에 직접 사용되지 않음
- **PDF 파서**: JavaScript 실행 엔진 없음 (pdfminer 텍스트만 추출)
- **Telemetry**: Sentry, Mixpanel, GA 등 **없음** (100% 깔끔)
- **`forget` API**: `/api/learned-patterns/forget` 존재 (pattern_id 또는 전체 삭제)

---

## 📊 우선순위 요약

| 우선순위 | 개수 | 영역 |
|---------|------|------|
| 🔴 Critical | 3 | Firebase 키, 서버 바인딩, 경로 검증 |
| 🟠 High | 8 | DoS, XSS, LAN 노출, 프라이버시 |
| 🟡 Medium | 8 | 정보 누출, 헤더, CSRF, 입력 검증 |
| 🔵 Low | 7 | TTL, 로그 로테이션, 의존성 |

---

## 🎯 즉시 조치 권장 (24시간 내)

1. `git rm --cached firebase-applet-config.json` + API 키 회전
2. `web_api.py:690`의 `default="0.0.0.0"` → `"127.0.0.1"`
3. `package.json`의 `dev` 스크립트 `--host=127.0.0.1`
4. `/api/file/extracted`에 `relative_to` 가드 추가
5. `DocxRenderer`에 DOMPurify 적용

## 🔒 JARVIS Privacy-First 원칙 준수 여부

| 원칙 | 준수 상태 |
|------|----------|
| All processing local | ✅ 모든 LLM, STT, TTS, embedding은 로컬 |
| No cloud dependencies (자동) | ⚠️ Google Fonts CDN 예외 |
| No cloud dependencies (사용자 트리거) | ⚠️ 날씨/웹검색 기능 — 설계상 의도 |
| No telemetry | ✅ Sentry/GA 등 일체 없음 |
| Data stays on device | ✅ 모든 DB는 `~/.jarvis-menubar/` 로컬 |
| User controls data | ⚠️ Learned patterns 삭제만 가능 (conversation_turns 삭제 API 없음) |

**결론**: 전반적으로 privacy-first 원칙을 잘 지키고 있으나, **Google Fonts CDN**과 **데이터 삭제 API 커버리지** 두 가지가 공식 원칙과 괴리가 있음. Critical 3건과 High 8건 수정 후 재감사 권장.

---

*본 보고서는 정적 코드 감사 + 일부 동적 검증 결과로, 런타임 동작 중 발생하는 동시성 이슈나 3rd-party 라이브러리 내부 취약점은 별도 감사가 필요합니다.*
