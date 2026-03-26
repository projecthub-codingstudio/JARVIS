# 한국 소버린 AI 모델 — JARVIS 적용 가능성 검토

Date: 2026-03-27
Purpose: 한국 정부 지원 소버린 AI 모델 3종의 JARVIS 프로젝트 적용 가능성 평가
Target Hardware: MacBook Pro M1 Max 64GB (로컬, 오프라인)

---

## 1. 요약 판정

| 모델 | 총 파라미터 | 활성 파라미터 | 4-bit 메모리 | M1 Max 64GB 실행 | 판정 |
|------|-----------|-------------|-------------|-----------------|------|
| Upstage Solar Open 100B | 102.6B (MoE) | 12B | ~58 GB | 불가 | 메모리 초과 |
| NC-AI VAETKI 112B | 112.2B (MoE) | 10.1B | ~63 GB | 불가 | 메모리 초과 |
| SKT A.X-K1 | 519B (MoE) | 33B | ~260 GB | 불가 | 완전 불가 (4배 초과) |

3개 모델 모두 JARVIS(M1 Max 64GB)에 적용 불가.

MoE(Mixture-of-Experts) 아키텍처의 핵심 제약: 활성 파라미터가 작아도 전체 expert 가중치가 메모리에 상주해야 한다. 토큰마다 다른 expert가 선택되므로 선택적 로딩이 불가능하다.

---

## 2. 모델별 상세 분석

### 2.1 Upstage Solar Open 100B

- HuggingFace: https://huggingface.co/upstage/Solar-Open-100B

#### 아키텍처

| 항목 | 값 |
|------|---|
| 총 파라미터 | 102.6B |
| 활성 파라미터/토큰 | 12B |
| 아키텍처 | MoE, 129 experts (128 routed + 1 shared), top-8 활성 |
| Hidden size | 4096 |
| Layers | 48 |
| Attention | GQA, 64 heads / 8 KV heads |
| 컨텍스트 | 128K (YaRN rope scaling) |
| 학습 데이터 | 19.7T 토큰 |
| 지식 기준일 | 2025-07 |

#### 메모리 요구량

| 포맷 | 크기 |
|------|------|
| BF16 | ~205 GB |
| INT8 | ~108 GB |
| MLX 4-bit | ~57.8 GB |
| GGUF Q4_K_M | ~62.3 GB |
| GGUF Q3_K_M | ~49.3 GB |
| GGUF Q2_K | ~37.7 GB |

MLX 4-bit(57.8GB): OS 메모리(~10GB) 감안 시 64GB에 적재 불가.
GGUF Q2_K(37.7GB): 겨우 적재 가능하나 품질 심각 저하 + KV cache 여유 없음.

#### 양자화 포맷 가용성

- MLX: mlx-community/Solar-Open-100B-4bit (57.8GB), 6bit, 8bit 존재 -- 생태계 가장 성숙
- GGUF: mradermacher/Solar-Open-100B-GGUF 등 다수 커뮤니티 변환
- AWQ: cyankiwi/Solar-Open-100B-AWQ-4bit 존재
- NotaAI INT4: nota-ai/Solar-Open-100B-NotaMoEQuant-Int4

#### 한국어 벤치마크

| 벤치마크 | Solar Open 100B | gpt-oss-120b |
|---------|:-:|:-:|
| KMMLU | 73.0 | 72.7 |
| KMMLU-Pro | 64.0 | 62.6 |
| CLIcK | 78.9 | 77.2 |
| HAE-RAE v1.1 | 73.3 | 70.8 |
| KBL (법률) | 65.5 | 62.8 |
| KorMedMCQA | 84.4 | 75.8 |
| Ko Arena Hard v2 | 79.9 | 79.5 |
| Ko-IFEval | 87.5 | 93.2 |

영어: MMLU 88.2, AIME 2024 91.7. 한국어 성능 매우 우수.

#### 라이선스

Upstage Solar License (Apache 2.0 기반):
- 상업적 사용 허용
- 파생 AI 모델명에 "Solar" 접두사 필수 (예: Solar-MyModel-v1)
- 인터페이스/문서에 "Built with Solar" 표시 필수
- 표준 오픈소스 라이선스가 아님 -- 브랜딩 요구사항 존재

#### M1 Max 64GB 실행 가능성

불가. MLX 4-bit(57.8GB)도 OS 오버헤드 감안 시 초과. Q2_K(37.7GB)는 이론상 적재 가능하나 KV cache + 시스템 메모리 부족, Q2_K 품질 저하로 벤치마크 이점 상실.

---

### 2.2 NC-AI Consortium VAETKI

- HuggingFace: https://huggingface.co/NC-AI-consortium-VAETKI/VAETKI

#### 모델 패밀리

| 모델 | 총 파라미터 | 활성 파라미터 | Experts | 컨텍스트 | 학습 토큰 |
|------|-----------|-------------|---------|---------|----------|
| VAETKI (flagship) | 112.2B | 10.1B | 128, top-8 | 32K | 9.8T |
| VAETKI-20B-A2B | 19.64B | 2.2B | 128, top-8 | 16K | 3.62T |
| VAETKI-7B-A1B | 7.25B | 1.2B | 64, top-5 | 16K | 1.86T |
| VAETKI-VL-7B-A1B | 7.58B | 1.2B | 64, top-5 | 16K | (멀티모달) |

13개 기관 협력 개발. 과기부 "독립형 AI 기반 모델" 사업. 2025년 12월 공개. MIT 라이선스.

특징: Multi-Latent Attention(MLA), KV cache 메모리 83% 절감, 126K 어휘 (한국어 20% 할당, 고한글 자모 포함).

#### 메모리 요구량

| 모델 | FP16 | Q4_K_M 추정 |
|------|------|------------|
| VAETKI-112B | ~209 GB | ~63 GB |
| VAETKI-20B-A2B | ~37 GB | ~11 GB |
| VAETKI-7B-A1B | ~14.5 GB | ~4.8 GB |

#### 양자화 포맷 가용성

- GGUF: 112B, VL-7B만 커뮤니티 변환 존재 (dororodoroddo/VAETKI-GGUF)
- MLX: 없음 -- 커스텀 아키텍처로 별도 구현 필요
- 중요: llama.cpp 메인라인 미지원. 비공식 포크(dororodoroddo/llama.cpp/tree/add-vaetki-support) 필요

#### 한국어 벤치마크

Flagship VAETKI-112B:

| 벤치마크 | VAETKI | GPT-OSS-120B |
|---------|:-:|:-:|
| KMMLU-Pro | 58.4 | 61.9 |
| CLIcK | 75.5 | 73.0 |
| KoBALT | 47.5 | 46.0 |
| HRM8K | 70.6 | 83.3 |
| IFEval | 86.0 | 83.6 |
| MMLU-Pro | 71.0 | 79.1 |

VAETKI-7B-A1B:

| 벤치마크 | 점수 |
|---------|-----|
| KMMLU-Pro | 24.2 |
| CLIcK | 40.6 |
| KoBALT | 11.9 |
| HRM8K | 26.5 |
| MATH500 | 61.8 |

7B 모델은 한국어 성능이 크게 부족. 20B 벤치마크는 미공개("to be updated").

#### 라이선스

MIT -- 가장 자유로운 라이선스. 상업적 사용, 수정, 배포 제한 없음.

#### M1 Max 64GB 실행 가능성

- 112B: 불가. Q4_K_M ~63GB, 메모리 초과.
- 20B-A2B: 이론상 가능 (Q4 ~11GB). 단, GGUF/MLX 미존재, 벤치마크 미공개.
- 7B-A1B: 적재 가능 (Q4 ~4.8GB). 단, MLX 미지원, 한국어 성능 EXAONE-3.5-7.8B 대비 크게 열세.

---

### 2.3 SKT A.X-K1

- HuggingFace: https://huggingface.co/skt/A.X-K1

#### 아키텍처

| 항목 | 값 |
|------|---|
| 총 파라미터 | 519B (518,983,059,456) |
| 활성 파라미터/토큰 | 33B |
| 아키텍처 | Sparse MoE, 192 routed + 1 shared expert, top-8 활성 |
| Layers | 61 (1 dense + 60 MoE) |
| Hidden size | 7,168 |
| Attention | Multi-Latent Attention (MLA) |
| 컨텍스트 | 128K |
| 학습 데이터 | ~10T 토큰 |
| 특수 기능 | Hybrid Think/Non-Think 추론, Multi-Token Prediction |
| 어휘 크기 | 163,840 |

#### 메모리 요구량

| 포맷 | 크기 |
|------|------|
| BF16 | ~1,038 GB |
| 4-bit | ~260 GB |
| 2-bit | ~130 GB |

260개 safetensor 샤드로 분할. 참조 배포 환경: 32 GPU x 4 노드.

#### 양자화 포맷 가용성

없음. GGUF, MLX, AWQ 어떤 양자화 포맷도 존재하지 않음.
커스텀 아키텍처(AXK1ForCausalLM)로 llama.cpp/MLX 미지원.
vLLM/SGLang 비공식 포크만 존재 (fort726/vllm, fort726/sglang).

#### 한국어 벤치마크 (Thinking 모드)

| 벤치마크 | A.X-K1 | DeepSeek-V3.1 | GLM-4.6 |
|---------|:-:|:-:|:-:|
| KMMLU | 80.2 | 76.5 | 79.9 |
| KMMLU-Redux | 77.9 | 75.9 | 78.2 |
| KMMLU-Pro | 68.1 | 71.4 | 71.8 |
| CLIcK | 84.9 | 84.5 | 84.9 |
| KoBALT | 48.8 | 59.7 | 59.2 |
| AIME25-ko (수학) | 86.9 | 78.1 | 75.9 |
| HRM8K (수학) | 89.4 | 84.3 | 83.9 |
| LiveCodeBench-ko | 73.1 | 66.2 | 55.9 |
| IFEval-ko | 81.0 | 79.2 | 85.8 |

한국어 수학/코딩 최강. 지식 벤치마크(KMMLU) 우수. KoBALT 약세(48.8).

#### 라이선스

Apache 2.0 -- 완전 자유 라이선스.

#### M1 Max 64GB 실행 가능성

완전 불가. 4-bit(~260GB)도 64GB의 4배. 2-bit(~130GB)도 2배 초과. 1-bit(~65GB)는 이론상 간신히 적재되나 품질 파괴.
서버급 모델로 로컬 실행 경로 자체가 존재하지 않음.

---

## 3. 현재 JARVIS 모델과 비교

| 기준 | EXAONE-3.5-7.8B (fast) | EXAONE-4.0-32B (deep) | Solar 100B | VAETKI 7B | VAETKI 20B | A.X-K1 |
|------|----------------------|---------------------|-----------|----------|-----------|--------|
| 4-bit 메모리 | ~4.5 GB | ~18 GB | ~58 GB | ~4.8 GB | ~11 GB | ~260 GB |
| 응답 속도 | 1.5초 | 8.8초 | 실행 불가 | 미검증 | 미검증 | 실행 불가 |
| 한국어 품질 | 3/3 정확 | 3/3 정확 | KMMLU 73.0 | KMMLU-Pro 24.2 | 미공개 | KMMLU 80.2 |
| MLX 지원 | 네이티브 | 네이티브 | 있음 | 없음 | 없음 | 없음 |
| GGUF 지원 | 있음 | 있음 | 있음 | 포크 필요 | 없음 | 없음 |
| 로컬 실행 | 가능 | 가능 | 불가 | 이론상 가능 | 이론상 가능 | 불가 |

---

## 4. 결론

### 즉시 적용 가능한 모델: 없음

3개 소버린 AI 모델의 flagship 버전은 모두 M1 Max 64GB에서 실용적으로 실행 불가.
공통 원인: MoE 아키텍처는 활성 파라미터와 무관하게 전체 expert 가중치를 메모리에 적재해야 함.

### 향후 모니터링 대상

| 우선순위 | 모델 | 모니터링 조건 | 이유 |
|---------|------|-------------|------|
| 1순위 | VAETKI-20B-A2B | 벤치마크 공개 + MLX/GGUF 메인라인 지원 | 4-bit ~11GB, deep tier 후보 가능성. MIT 라이선스 |
| 2순위 | Solar Open 100B | 128GB+ 메모리 기기 업그레이드 시 | 한국어 성능 탁월, MLX 생태계 성숙 |
| 3순위 | VAETKI-7B-A1B | MLX 지원 + 한국어 성능 개선 버전 | MIT 라이선스. 현재는 성능 부족 |
| 대상 외 | A.X-K1 | 서버 배포 환경에서만 가치 | 로컬 실행 경로 없음 |

### 현재 최적 유지

EXAONE-3.5-7.8B (fast) + EXAONE-4.0-32B (deep) 조합이 M1 Max 64GB에서 여전히 최적.

소버린 AI 모델이 로컬 실행에 의미를 가지려면:
1. 더 작은 증류(distilled) 모델 출시, 또는
2. 128GB+ Apple Silicon 기기 업그레이드, 또는
3. MLX/GGUF 생태계 성숙 (특히 VAETKI 계열)

이 필요하다.

---

## 5. 참고 자료

### Solar Open 100B
- https://huggingface.co/upstage/Solar-Open-100B
- https://huggingface.co/mlx-community/Solar-Open-100B-4bit
- https://huggingface.co/mradermacher/Solar-Open-100B-GGUF

### VAETKI
- https://huggingface.co/NC-AI-consortium-VAETKI/VAETKI
- https://huggingface.co/nc-ai-consortium/VAETKI-7B-A1B
- https://huggingface.co/nc-ai-consortium/VAETKI-20B-A2B
- https://huggingface.co/dororodoroddo/VAETKI-GGUF

### SKT A.X-K1
- https://huggingface.co/skt/A.X-K1
