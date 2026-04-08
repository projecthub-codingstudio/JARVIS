# JARVIS 설치 가이드

> 최종 업데이트: 2026-04-08

MacBook Pro M1 Max (64GB)에서 JARVIS를 설치하고 실행하는 전체 과정을 설명합니다.

---

## 목차

1. [시스템 요구사항](#1-시스템-요구사항)
2. [사전 준비](#2-사전-준비)
3. [저장소 클론](#3-저장소-클론)
4. [백엔드 설치](#4-백엔드-설치)
5. [프론트엔드 설치](#5-프론트엔드-설치)
6. [Knowledge Base 설정](#6-knowledge-base-설정)
7. [LLM 모델 다운로드](#7-llm-모델-다운로드)
8. [실행](#8-실행)
9. [설치 확인](#9-설치-확인)
10. [환경 변수 설정](#10-환경-변수-설정)
11. [트러블슈팅](#11-트러블슈팅)
12. [업데이트](#12-업데이트)

---

## 1. 시스템 요구사항

### 필수

| 항목 | 요구사항 |
|------|---------|
| **하드웨어** | Apple Silicon Mac (M1/M2/M3/M4) |
| **메모리** | 최소 32GB, 권장 64GB 통합 메모리 |
| **저장공간** | 최소 20GB 여유 (모델 + 인덱스 + KB) |
| **OS** | macOS 14+ (Sonoma/Sequoia/Tahoe) |
| **Python** | 3.12 이상 |
| **Node.js** | 18 이상 (권장 20+) |

### 메모리 사용량 참고

| 구성요소 | 메모리 |
|---------|--------|
| EXAONE-3.5-7.8B (4bit) | ~6GB |
| Gemma 4 E4B (4bit) | ~5.3GB |
| BGE-M3 임베딩 | ~2GB |
| Reranker | ~0.5GB |
| 백엔드 프로세스 | ~1GB |
| **합계 (순차 로드)** | **~15GB peak** |

> 모델은 순차 로드됩니다. 동시에 모든 모델이 메모리에 올라가지 않습니다.

---

## 2. 사전 준비

### 2.1 Homebrew 설치 (미설치 시)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2.2 Python 3.12 설치

```bash
brew install python@3.12

# 버전 확인
python3.12 --version
# Python 3.12.x
```

### 2.3 Node.js 설치

```bash
brew install node

# 버전 확인
node --version  # v18+ 이상
npm --version   # 9+ 이상
```

### 2.4 Git 설치 (미설치 시)

```bash
brew install git
git --version
```

---

## 3. 저장소 클론

```bash
# 원하는 디렉토리에서 실행
git clone https://github.com/projecthub-codingstudio/JARVIS.git
cd JARVIS
```

---

## 4. 백엔드 설치

### 4.1 Python 가상환경 생성

```bash
cd alliance_20260317_130542

# 가상환경 생성
python3.12 -m venv .venv

# 가상환경 활성화
source .venv/bin/activate

# pip 업그레이드
pip install --upgrade pip
```

### 4.2 핵심 의존성 설치

```bash
# 메인 패키지 + 웹 API + 개발도구
pip install -e ".[web,dev]"
```

이 명령으로 설치되는 주요 패키지:

| 패키지 | 용도 |
|--------|------|
| `mlx`, `mlx-lm` | Apple Silicon LLM 추론 엔진 |
| `sentence-transformers` | BGE-M3 임베딩 모델 |
| `lancedb` | 벡터 데이터베이스 |
| `kiwipiepy` | 한국어 형태소 분석 |
| `pymupdf` | PDF 파싱 |
| `python-docx` | DOCX 파싱 |
| `python-pptx` | PPTX 파싱 |
| `openpyxl` | XLSX 파싱 |
| `python-hwpx`, `pyhwp` | HWP/HWPX 파싱 |
| `fastapi`, `uvicorn` | 웹 API 서버 |
| `watchdog` | 파일 변경 감지 |
| `psutil` | 시스템 리소스 모니터링 |

### 4.3 Gemma 4 Vision 지원 (선택)

문서 직접 분석 및 이미지 Q&A를 위해 `mlx-vlm`을 설치합니다:

```bash
pip install "mlx-vlm>=0.4.4"
```

### 4.4 tree-sitter 코드 파서 (선택)

Python/JS/TS 소스 코드의 정밀한 AST 기반 청킹을 위해:

```bash
pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-typescript
```

> 미설치 시 regex fallback으로 동작합니다 (class/def 경계 기반 분할).

### 4.5 Cross-Encoder Reranker 모델 다운로드

첫 실행 시 자동 다운로드되지만, 미리 받아둘 수 있습니다:

```bash
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')"
```

### 4.6 설치 확인

```bash
# 가상환경 활성화 상태에서
python -c "
import mlx; print(f'MLX: {mlx.__version__}')
import mlx_lm; print(f'mlx-lm: {mlx_lm.__version__}')
import lancedb; print(f'LanceDB: {lancedb.__version__}')
import kiwipiepy; print('Kiwi: OK')
import pymupdf; print('PyMuPDF: OK')
import fastapi; print('FastAPI: OK')
try:
    import mlx_vlm; print('mlx-vlm: OK (Gemma vision ready)')
except ImportError:
    print('mlx-vlm: NOT installed (vision disabled)')
"
```

---

## 5. 프론트엔드 설치

```bash
cd ../ProjectHub-terminal-architect

# 의존성 설치
npm install

# 환경 설정 파일 생성
cp .env.example .env
```

`.env` 파일 내용 확인:

```env
# JARVIS Web API URL
VITE_JARVIS_API_URL=http://localhost:8000

# WebSocket URL (optional, for real-time streaming)
VITE_JARVIS_WS_URL=ws://localhost:8000/ws
```

### 빌드 확인

```bash
npm run build
# ✓ built in ~4s
```

---

## 6. Knowledge Base 설정

JARVIS가 검색하고 분석할 문서를 넣는 디렉토리입니다.

### 6.1 기본 위치

```bash
# 프로젝트 루트에 knowledge_base 디렉토리 생성
cd ..  # JARVIS 루트로 이동
mkdir -p knowledge_base
```

### 6.2 문서 추가

지원하는 파일을 `knowledge_base/` 에 넣으면 자동으로 인덱싱됩니다:

```bash
# 예시: 하위 디렉토리 구조
knowledge_base/
├── coding/           # 소스 코드
│   ├── app.py
│   └── utils.swift
├── docs/             # 문서
│   ├── architecture.md
│   └── manual.pdf
├── 전자책/            # PDF 전자책
│   └── Effective_C++.pdf
└── data/             # 스프레드시트
    └── report.xlsx
```

### 6.3 지원 파일 형식 (60+ 확장자)

| 카테고리 | 확장자 |
|---------|--------|
| **문서** | `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.hwp`, `.hwpx` |
| **텍스트** | `.md`, `.txt`, `.rst`, `.csv`, `.tsv`, `.log` |
| **코드** | `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.swift`, `.java`, `.kt`, `.go`, `.rs`, `.cpp`, `.c`, `.cs`, `.rb`, `.php`, `.sh` |
| **웹** | `.html`, `.htm`, `.css`, `.scss`, `.svg` |
| **데이터** | `.json`, `.yaml`, `.yml`, `.xml`, `.sql` |
| **설정** | `.toml`, `.ini`, `.cfg`, `.conf`, `.env` |

> 미등록 확장자도 텍스트 자동 감지로 인덱싱을 시도합니다.

### 6.4 커스텀 위치 지정

```bash
# 환경 변수로 다른 경로 지정
export JARVIS_KNOWLEDGE_BASE=/path/to/your/documents
```

---

## 7. LLM 모델 다운로드

### 7.1 기본 모델 (EXAONE-3.5-7.8B)

첫 실행 시 자동 다운로드됩니다. 미리 받으려면:

```bash
source alliance_20260317_130542/.venv/bin/activate

# HuggingFace에서 모델 다운로드 허용
HF_HUB_OFFLINE=0 python -c "
from mlx_lm import load
model, tokenizer = load('mlx-community/EXAONE-3.5-7.8B-Instruct-4bit')
print('EXAONE-3.5-7.8B loaded successfully')
del model, tokenizer
"
```

> 약 4.5GB 다운로드, 최초 1회만 필요합니다.

### 7.2 Gemma 4 E4B (문서 분석 + 비전)

128K 컨텍스트로 긴 문서 분석에 사용됩니다:

```bash
HF_HUB_OFFLINE=0 python -c "
from mlx_vlm import load
model, processor = load('mlx-community/gemma-4-E4B-it-4bit')
print('Gemma 4 E4B loaded successfully')
del model, processor
"
```

> 약 5.3GB 다운로드.

### 7.3 BGE-M3 임베딩 모델

벡터 검색용 임베딩 모델 (첫 실행 시 자동 다운로드):

```bash
HF_HUB_OFFLINE=0 python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-m3')
print('BGE-M3 loaded successfully')
del model
"
```

> 약 2.2GB 다운로드.

### 7.4 모델 저장 위치

모든 모델은 HuggingFace 캐시에 저장됩니다:

```
~/.cache/huggingface/hub/
├── models--mlx-community--EXAONE-3.5-7.8B-Instruct-4bit/
├── models--mlx-community--gemma-4-E4B-it-4bit/
├── models--BAAI--bge-m3/
└── models--cross-encoder--mmarco-mMiniLMv2-L12-H384-v1/
```

---

## 8. 실행

### 8.1 원클릭 실행 (권장)

```bash
cd ProjectHub-terminal-architect
./scripts/start.sh
```

출력 예시:
```
▶ Starting JARVIS backend (port 8000)...
  PID: 12345
▶ Starting frontend dev server (port 3000)...
  PID: 12346

⏳ Waiting for backend...
✓ Backend ready

═══════════════════════════════════════════
  Frontend:  http://localhost:3000
  Backend:   http://localhost:8000
  Logs:      .pids/*.log
  Stop:      scripts/stop.sh
═══════════════════════════════════════════
```

### 8.2 수동 실행 (개별 터미널)

**터미널 1: 백엔드**
```bash
cd alliance_20260317_130542
source .venv/bin/activate
python -m jarvis.web_api --port 8000
```

**터미널 2: 프론트엔드**
```bash
cd ProjectHub-terminal-architect
npm run dev
```

### 8.3 종료

```bash
cd ProjectHub-terminal-architect
./scripts/stop.sh
```

### 8.4 모델 체인 설정

```bash
# 기본: EXAONE + stub fallback
JARVIS_MENU_BAR_MODEL_CHAIN="exaone3.5:7.8b,stub" ./scripts/start.sh

# Gemma 4 우선 (문서 분석 + 비전)
JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e4b,stub" ./scripts/start.sh

# 하이브리드: Gemma → EXAONE → stub
JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e4b,exaone3.5:7.8b,stub" ./scripts/start.sh

# LLM 없이 (검색만)
JARVIS_MENU_BAR_MODEL_CHAIN="stub" ./scripts/start.sh
```

---

## 9. 설치 확인

### 9.1 백엔드 Health Check

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

정상 응답:
```json
{
    "health": {
        "healthy": true,
        "status_level": "ready",
        "chunk_count": 22692,
        "doc_count": 207,
        "embedding_count": 22692
    }
}
```

### 9.2 프론트엔드 접속

브라우저에서 http://localhost:3000 접속:
- 좌측 nav에 6개 탭 (Home, Terminal, Documents, Explorer, Skills, Admin)
- 우측 상단에 `ONLINE` 상태 배지
- Terminal에서 질문 입력 가능

### 9.3 기본 테스트

Terminal에서 입력:
```
안녕하세요
```
→ JARVIS가 응답하면 LLM 정상 동작

```
knowledge_base 에 있는 문서 보여줘
```
→ 검색 결과가 나오면 인덱싱 + 검색 정상 동작

### 9.4 테스트 스위트 실행

```bash
cd alliance_20260317_130542
source .venv/bin/activate
python -m pytest tests/ -v --tb=short
# 420+ tests
```

---

## 10. 환경 변수 설정

| 환경 변수 | 기본값 | 설명 |
|----------|--------|------|
| `JARVIS_KNOWLEDGE_BASE` | `./knowledge_base/` | Knowledge Base 경로 |
| `JARVIS_DATA_DIR` | `~/.jarvis-menubar/` | DB, 벡터 인덱스 저장 경로 |
| `JARVIS_MENU_BAR_MODEL_CHAIN` | `exaone3.5:7.8b,stub` | LLM 모델 체인 (쉼표 구분) |
| `JARVIS_MENU_BRIDGE_TIMEOUT_SECONDS` | `50` | LLM 추론 타임아웃 (초) |
| `VITE_JARVIS_API_URL` | `http://localhost:8000` | 프론트엔드 API 주소 |
| `VITE_JARVIS_WS_URL` | `ws://localhost:8000/ws` | WebSocket 주소 |
| `HF_HUB_OFFLINE` | `1` (기본 설정) | HuggingFace 오프라인 모드 |

---

## 11. 트러블슈팅

### "No module named 'mlx'" 에러

```bash
# Apple Silicon Mac이 아닌 경우 MLX를 사용할 수 없습니다
# Intel Mac에서는 stub 모드로 실행:
JARVIS_MENU_BAR_MODEL_CHAIN="stub" ./scripts/start.sh
```

### "Backend Offline" 표시

```bash
# 백엔드 로그 확인
cat ProjectHub-terminal-architect/.pids/backend.err

# 포트 충돌 확인
lsof -i :8000

# 수동 재시작
./scripts/stop.sh && ./scripts/start.sh
```

### 모델 다운로드 실패

```bash
# 오프라인 모드 해제 후 재시도
HF_HUB_OFFLINE=0 python -c "from mlx_lm import load; load('mlx-community/EXAONE-3.5-7.8B-Instruct-4bit')"
```

### 한국어 검색이 안 될 때

```bash
# Kiwi 형태소 분석기 확인
python -c "from kiwipiepy import Kiwi; k = Kiwi(); print(k.tokenize('한국어 테스트'))"

# 형태소 백필이 아직 안 된 경우 (인덱싱 직후):
# 10분 주기로 자동 실행됩니다. 또는 POST /api/reindex로 수동 트리거.
```

### PDF 파싱 에러

```bash
# PyMuPDF 설치 확인
python -c "import pymupdf; print(pymupdf.version)"

# 재설치
pip install --force-reinstall pymupdf
```

### 메모리 부족 (OOM)

```bash
# 경량 모델로 전환
JARVIS_MENU_BAR_MODEL_CHAIN="gemma4:e2b,stub" ./scripts/start.sh

# 또는 LLM 없이 검색만
JARVIS_MENU_BAR_MODEL_CHAIN="stub" ./scripts/start.sh
```

### npm install 실패

```bash
# Node.js 버전 확인 (18+ 필요)
node --version

# 캐시 정리 후 재설치
cd ProjectHub-terminal-architect
rm -rf node_modules package-lock.json
npm install
```

---

## 12. 업데이트

### 12.1 코드 업데이트

```bash
cd JARVIS
git pull origin main

# 백엔드 의존성 업데이트
cd alliance_20260317_130542
source .venv/bin/activate
pip install -e ".[web,dev]"

# 프론트엔드 의존성 업데이트
cd ../ProjectHub-terminal-architect
npm install

# 재시작
./scripts/stop.sh && ./scripts/start.sh
```

### 12.2 Knowledge Base 리인덱스

새 문서를 추가한 후 즉시 인덱싱하려면:

```bash
# 자동: knowledge_base/ 에 파일 추가 → FileWatcher가 자동 감지

# 수동: 전체 리인덱스
curl -X POST http://localhost:8000/api/reindex

# 웹 UI: Admin 탭 → Reindex 버튼
```

---

## 부록: 디렉토리 구조

설치 완료 후 디렉토리 구조:

```
JARVIS/
├── alliance_20260317_130542/        # Python 백엔드
│   ├── .venv/                       # Python 가상환경
│   ├── src/jarvis/                  # 소스 코드
│   ├── tests/                       # 테스트 (420+)
│   └── pyproject.toml               # Python 의존성
├── ProjectHub-terminal-architect/   # React 프론트엔드
│   ├── node_modules/                # npm 패키지
│   ├── src/                         # 소스 코드
│   ├── dist/                        # 빌드 결과물
│   ├── scripts/
│   │   ├── start.sh                 # 원클릭 실행
│   │   └── stop.sh                  # 종료
│   ├── .env                         # 환경 설정
│   └── package.json                 # npm 의존성
├── knowledge_base/                  # 사용자 문서 (git-ignored)
├── docs/                            # 아키텍처 문서
│   ├── JARVIS_Query_Pipeline_Architecture.md
│   ├── JARVIS_Indexing_Pipeline_Detail.md
│   └── JARVIS_Installation_Guide.md  # 이 문서
├── README.md
├── LICENSE
└── .gitignore
```

### 런타임 데이터 위치

```
~/.jarvis-menubar/
├── jarvis.db                        # SQLite DB (문서, 청크, 피드백)
└── vectors.lance/                   # LanceDB 벡터 인덱스

~/.cache/huggingface/hub/            # HuggingFace 모델 캐시
├── models--mlx-community--EXAONE-3.5-7.8B-Instruct-4bit/
├── models--mlx-community--gemma-4-E4B-it-4bit/
├── models--BAAI--bge-m3/
└── models--cross-encoder--mmarco-mMiniLMv2-L12-H384-v1/
```
