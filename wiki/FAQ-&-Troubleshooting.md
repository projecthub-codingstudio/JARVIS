# FAQ & Troubleshooting

## Frequently Asked Questions

### General

**Q: Can I run JARVIS without Ollama?**
Yes. MLX is the primary backend and doesn't require Ollama. Ollama is only needed as a fallback if MLX encounters issues with a specific model.

**Q: Does JARVIS work completely offline?**
Yes. All models run locally on Apple Silicon. No internet connection required after initial setup and model download.

**Q: How much memory does JARVIS need?**
JARVIS is designed for 16GB worst-case memory budget. Models are loaded sequentially (one at a time), so peak usage is ~8-10GB for the largest model (Qwen3-14B Q4). The Governor automatically downgrades to smaller models if memory pressure is detected.

**Q: Can I use my own documents?**
Yes. Place files in the `knowledge_base/` directory. JARVIS automatically indexes them on startup and watches for changes in real-time. Supported: PDF, DOCX, XLSX, HWP, Markdown, code files, and 80+ formats.

**Q: Is JARVIS Korean-only?**
No. JARVIS is **Korean-first** (optimized for Korean documents and queries) but fully supports English. The AI Planner translates Korean keywords to English for broader search coverage.

**Q: Can I run JARVIS on Intel Mac?**
No. JARVIS requires Apple Silicon (M1/M2/M3/M4) for MLX and Metal acceleration. Intel Macs are not supported.

**Q: What's the difference between the CLI and Menu Bar app?**
Both use the same `RuntimeContext` and Orchestrator pipeline. The CLI is a terminal-based REPL; the Menu Bar is a native macOS SwiftUI app. They share identical backend logic.

### Models

**Q: Which model should I use?**
- **Default (Qwen3-14B)**: Best quality, recommended for most use
- **Fast (EXAONE-3.5-7.8B)**: Faster responses, lower memory, good for quick queries
- The Governor automatically selects based on system resources

**Q: Can I use other models?**
The `--model` flag accepts Ollama model identifiers. For MLX, models need to be in MLX format. The Governor's model map defines which models map to which tiers.

**Q: How do I download models?**
For Ollama: `ollama pull qwen3:14b` or `ollama pull exaone3.5:7.8b`. MLX models are loaded through the mlx-lm library.

### Voice

**Q: Why can't I record audio?**
Check macOS microphone permissions: System Settings → Privacy & Security → Microphone. JARVIS performs a TCC permission preflight check — if denied, you'll see a clear error message.

**Q: Can I change the recording duration?**
Yes. Set `JARVIS_PTT_SECONDS=15` (or any duration in seconds) as an environment variable.

**Q: Can I choose a specific microphone?**
Yes. Use `--voice-device="Device Name"` or set `JARVIS_PTT_DEVICE` environment variable.

---

## Troubleshooting

### Memory Pressure / Governor Degraded Mode

**Symptoms**: Slower responses, "DEGRADED" or "RESTRICTED" governor mode, smaller model being used.

**Causes & Solutions**:

| Condition | What's Happening | Solution |
|-----------|-----------------|----------|
| Memory ≥ 70% | Governor downgrades tier | Close memory-heavy apps (browser, IDE) |
| Swap ≥ 2,048 MB | Forced to fast tier | Reduce open apps, restart JARVIS |
| Swap ≥ 4,096 MB | SHUTDOWN mode (search only) | Restart macOS to clear swap |
| Thermal = serious | Forced to fast tier | Let the machine cool down |

**Check current status** on startup:
```
Memory: 72% (46.1 / 64.0 GB)  Swap: 1024 MB
Governor: DEGRADED  Tier: fast
```

### Parser Dependencies Missing

**Symptoms**: Some file types aren't being indexed, test warnings about skipped tests.

**Solution**: Install optional parsers:
```bash
pip install pymupdf          # PDF
pip install python-docx      # Word
pip install python-pptx      # PowerPoint
pip install openpyxl         # Excel
pip install python-hwpx      # HWP (new format)
pip install pyhwp            # HWP (legacy format)
```

JARVIS gracefully degrades when a parser is missing — other file types continue to work normally.

### Microphone Permission Denied

**Symptoms**: Voice mode fails with TCC permission error.

**Solution**:
1. Open System Settings → Privacy & Security → Microphone
2. Enable permission for Terminal (or your terminal app)
3. Restart the terminal
4. Try `python -m jarvis --voice-ptt` again

### Slow Morphological Analysis

**Symptoms**: Indexing takes longer than expected on large document collections.

**Solution**: Kiwi morphological analysis is CPU-intensive. For large knowledge bases:
- Index during idle time (JARVIS handles this automatically)
- The Governor's indexing controls will pause indexing if the system is under thermal or battery pressure
- Batch size is managed by the async pipeline

### Model Download Fails

**Symptoms**: Ollama model pull fails or times out.

**Solution**:
```bash
# Check Ollama is running
ollama list

# Restart Ollama
ollama serve

# Re-pull the model
ollama pull qwen3:14b
```

### Database Issues

**Symptoms**: SQLite errors on startup, data corruption warnings.

**Solution**:
- JARVIS runs an integrity check on startup
- If integrity fails → enters read-only mode with rebuild recommendation
- To rebuild: delete `~/.jarvis/jarvis.db` and restart (triggers full re-index)

### Vector Index Not Active

**Symptoms**: "Vector index: inactive" on startup, no vector search results.

**Solution**: The vector index requires BGE-M3 embeddings:
```bash
# Verify sentence-transformers is installed
pip install sentence-transformers

# The vector backfill runs automatically after FTS indexing
# Check logs for embedding progress
JARVIS_LOG_FORMAT=json python -m jarvis
```

## Known Issues (Beta 1)

These are acknowledged limitations in the current release:

| Category | Issue | Status |
|----------|-------|--------|
| UI | Menu bar not fully polished | Post-beta work |
| Voice | Live loop needs polish | Implemented, needs hardening |
| Voice | Mic device not in menu bar UI | Planned |
| Retrieval | Citation verification is conservative | Iterating |
| Runtime | Reranker deferred | Not blocking beta |
| Environment | Optional parser deps may be missing | Graceful degradation |

For the full list, see [KNOWN_ISSUES_BETA_1.md](https://github.com/projecthub-codingstudio/JARVIS/blob/main/alliance_20260317_130542/docs/KNOWN_ISSUES_BETA_1.md).

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/projecthub-codingstudio/JARVIS/issues)
- **Wiki**: You're here! Browse the sidebar for detailed documentation.

## Related Pages

- [[Getting Started]] — Installation guide
- [[Configuration]] — All settings and environment variables
- [[Security Model]] — Governor thresholds and safety controls

---

## :kr: 한국어

# FAQ & 문제 해결

### 자주 묻는 질문

**Q: Ollama 없이 실행 가능한가요?**
네. MLX가 기본 백엔드이며 Ollama 없이 동작합니다.

**Q: 완전 오프라인으로 동작하나요?**
네. 초기 설정과 모델 다운로드 후에는 인터넷 연결이 필요 없습니다.

**Q: 메모리가 얼마나 필요한가요?**
16GB worst-case 설계. 모델은 순차 로딩되며, 피크 사용량은 ~8-10GB입니다.

**Q: 한국어 전용인가요?**
아닙니다. **한국어 우선**이지만 영어도 완전 지원합니다.

**Q: Intel Mac에서 실행 가능한가요?**
아닙니다. Apple Silicon (M1/M2/M3/M4) 필수입니다.

### 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 느린 응답, DEGRADED 모드 | 메모리 부족 | 무거운 앱 닫기, 재시작 |
| 일부 파일 미인덱싱 | 파서 의존성 누락 | `pip install pymupdf python-docx` 등 |
| 음성 모드 실패 | TCC 마이크 권한 | 시스템 설정 → 개인정보 → 마이크 |
| SQLite 오류 | DB 손상 | `~/.jarvis/jarvis.db` 삭제 후 재시작 |
| 벡터 인덱스 비활성 | sentence-transformers 미설치 | `pip install sentence-transformers` |
