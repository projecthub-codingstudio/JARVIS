# Getting Started

Get JARVIS up and running on your Apple Silicon Mac.

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| macOS | Tahoe (26.x) or later | Apple Silicon required (M1/M2/M3/M4) |
| Python | 3.12+ | `brew install python@3.12` |
| Ollama | Latest | Fallback LLM backend — [ollama.com](https://ollama.com) |
| Xcode CLI Tools | Latest | `xcode-select --install` (for whisper.cpp, MLX) |

## Installation

```bash
# Clone the repository
git clone https://github.com/projecthub-codingstudio/JARVIS.git
cd JARVIS/alliance_20260317_130542

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install JARVIS with all dependencies
pip install -e ".[dev]"
```

### Optional: Pull Ollama Models

If using Ollama as the LLM backend:

```bash
# Default model (recommended)
ollama pull qwen3:14b

# Faster, lighter alternative
ollama pull exaone3.5:7.8b
```

## First Run

```bash
# Start JARVIS (interactive REPL)
python -m jarvis

# Or specify a model
python -m jarvis --model=exaone3.5:7.8b
```

On startup, JARVIS displays system status:

```
JARVIS v0.1.0-beta1
Memory: 42% (27.1 / 64.0 GB)  Swap: 0 MB
Thermal: nominal  Battery: AC
Governor: NORMAL  Tier: balanced
Chunks indexed: 1,247  Vector index: active
>
```

## Your First Query — "Hello World"

1. **Add documents** to the knowledge base:
   ```bash
   mkdir -p knowledge_base
   cp ~/Documents/my-report.pdf knowledge_base/
   ```

2. **Start JARVIS** and ask a question:
   ```bash
   python -m jarvis
   > 이 보고서의 핵심 결론이 뭐야?
   ```

3. **See citations** in the response:
   ```
   보고서의 핵심 결론은 ...

   📎 Sources:
     [1] my-report.pdf (PDF) — "핵심 결론은..."
   ```

JARVIS will automatically index the file on startup. Subsequent file additions are detected in real-time by the file watcher.

## Voice Modes

```bash
# Process a pre-recorded audio file
python -m jarvis --voice-file=question.wav

# Push-to-talk: record once, get answer
python -m jarvis --voice-ptt

# With TTS output
python -m jarvis --voice-file=question.wav --voice-output=answer.wav
```

See [[Voice Pipeline]] for detailed voice mode documentation.

## Menu Bar App

Build the native macOS menu bar companion app:

1. Open `macos/JarvisMenuBar/` in Xcode
2. Build and run (⌘R)
3. JARVIS icon appears in the menu bar
4. Type queries or use voice directly from the menu bar

See [[Menu Bar App]] for architecture details.

## Running Tests

```bash
# All tests (357 passing)
python -m pytest tests/ -v

# By category
python -m pytest tests/unit/ -v          # Unit tests
python -m pytest tests/integration/ -v   # Integration tests
python -m pytest tests/e2e/ -v           # End-to-end tests

# Performance benchmarks
python -m pytest tests/perf/ -v -m perf
```

## Supported Document Formats

| Format | Extension | Parser |
|--------|-----------|--------|
| PDF | `.pdf` | PyMuPDF |
| Word | `.docx` | python-docx |
| PowerPoint | `.pptx` | python-pptx |
| Excel | `.xlsx` | openpyxl |
| HWP (Korean) | `.hwpx`, `.hwp` | python-hwpx, pyhwp |
| Text | `.md`, `.txt`, `.csv` | Built-in |
| Code | `.py`, `.js`, `.java`, ... | Built-in |
| Data | `.json`, `.yaml`, `.xml` | Built-in |

80+ file extensions supported. See [[Retrieval Pipeline]] for the full indexing architecture.

## Next Steps

- [[Architecture Overview]] — Understand how JARVIS works
- [[Configuration]] — Customize settings and tune search parameters
- [[Design Decisions]] — Learn why these technologies were chosen

---

## :kr: 한국어

# 시작하기

Apple Silicon Mac에서 JARVIS를 설치하고 실행하는 방법입니다.

### 필수 요건

| 요구 사항 | 버전 | 비고 |
|-----------|------|------|
| macOS | Tahoe (26.x) 이상 | Apple Silicon 필수 (M1/M2/M3/M4) |
| Python | 3.12+ | `brew install python@3.12` |
| Ollama | 최신 | LLM 백엔드 fallback — [ollama.com](https://ollama.com) |
| Xcode CLI Tools | 최신 | `xcode-select --install` |

### 설치

```bash
git clone https://github.com/projecthub-codingstudio/JARVIS.git
cd JARVIS/alliance_20260317_130542
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 첫 실행

```bash
python -m jarvis                          # 대화형 REPL
python -m jarvis --model=exaone3.5:7.8b   # 모델 지정
```

### 첫 질문 해보기

1. `knowledge_base/` 폴더에 문서를 넣습니다 (PDF, DOCX, HWP 등)
2. `python -m jarvis`로 시작합니다
3. 질문하면 출처와 함께 답변을 받습니다

### 음성 모드

```bash
python -m jarvis --voice-file=질문.wav     # 파일 입력
python -m jarvis --voice-ptt              # 한 번 녹음 → 답변
```

### 테스트

```bash
python -m pytest tests/ -v                # 전체 357개 테스트
```
