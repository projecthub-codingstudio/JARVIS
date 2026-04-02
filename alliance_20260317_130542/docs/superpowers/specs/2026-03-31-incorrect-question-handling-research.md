# Research: Handling Incorrect or Unsupported Questions

Date: 2026-03-31

## Problem

Current JARVIS behavior still leans toward "answer if anything was retrieved." When the user's question has a wrong premise, refers to the wrong entity, or is simply too ambiguous, the system can attach loosely related evidence and produce a confident but wrong answer.

This is not mainly a generation problem. It is an answerability decision problem:

- Should JARVIS answer?
- Should JARVIS ask a clarification question?
- Should JARVIS explicitly abstain and say the evidence does not support an answer?

## What The Current Code Does

The current pipeline already has retrieval, evidence scoring, and post-generation verification, but it does not yet have a strong pre-generation abstention policy.

- `src/jarvis/core/orchestrator.py`
  - Stops only when evidence is empty.
  - If any evidence exists, it proceeds to generation.
- `src/jarvis/retrieval/evidence_builder.py`
  - Uses boosted ranking and keeps low-scoring evidence.
  - `MIN_RELEVANCE_SCORE` is very low (`0.01`), so weak matches survive.
- `src/jarvis/runtime/mlx_runtime.py`
  - Citation verification runs after generation.
  - Verification warnings do not block the answer.
  - Streaming returns the answer before verification completes.
- `src/jarvis/runtime/system_prompt.py`
  - The prompt says irrelevant evidence may be ignored and the model may answer from its own knowledge.
  - For a local workspace QA product, this increases the risk of unsupported answers.

In short: the system has retrieval and verification, but no strong "do not answer" gate between them.

## Research Summary

### 1. Abstention is a first-class capability, not a fallback

Rajpurkar et al. (SQuAD 2.0) showed that QA systems must learn to determine when no answer is supported and abstain, not just answer when possible.

Implication for JARVIS:

- "No answer" must be treated as a correct product behavior.
- Wrong-premise and unsupported questions should map to an abstain path, not a best-effort answer path.

### 2. Model confidence alone is not enough

Kamath et al. showed that under domain shift, raw QA confidence is overconfident and poor for abstention. A separate calibrator performs better than relying on model probability alone.

Implication for JARVIS:

- Do not trust only LLM confidence or only top retrieval score.
- Add a dedicated answerability calibrator or gate using retrieval and query features.

### 3. Retrieval quality must be evaluated before generation

CRAG proposes a lightweight retrieval evaluator that estimates retrieval quality and triggers different actions depending on confidence.

Implication for JARVIS:

- Add a retrieval-quality stage before generation.
- If evidence quality is low, do not generate a direct answer.
- Use alternate actions: abstain, ask a clarification question, or show candidate sources.

### 4. Adaptive self-reflection helps, but it is not enough by itself

Self-RAG shows that adaptive retrieval and self-reflection improve factuality versus fixed retrieval pipelines.

Implication for JARVIS:

- Self-check style signals are useful.
- But they should support an explicit policy gate, not replace it.

### 5. Ambiguity is common and should trigger clarification

AmbigQA shows ambiguous questions are common in open-domain QA. Lee et al. show a useful decomposition into:

- ambiguity detection
- clarification question generation
- clarification-based QA

Implication for JARVIS:

- Some bad answers are not "missing evidence" problems.
- They are ambiguity problems and should trigger a clarification question instead.

Examples:

- wrong entity reference
- missing file or document scope
- multiple plausible interpretations
- vague references like "that file", "the schedule", "the model"

### 6. User feedback helps, but should not be the first-line fix

Gao et al. show QA systems can improve over time with human feedback. But Liu et al. show real user feedback is a noisy learning signal with mixed gains depending on task and feedback form.

Implication for JARVIS:

- Collect feedback, but do not depend on feedback-trained learning as the primary defense.
- First reduce wrong answers online with gating and clarification.
- Then use feedback offline for threshold tuning, failure mining, and later model training.

### 7. Claim-level verification still misses entity-mixing failures

Chiang and Lee show a generation can consist of individually verifiable facts that still combine into a wrong paragraph due to entity ambiguity.

Implication for JARVIS:

- Current claim-level citation verification is necessary but insufficient.
- The system also needs entity-consistency and premise-consistency checks.

## Recommendation

### Decision

The primary strategy should be:

1. Add answerability and ambiguity gating before generation.
2. Prefer clarification or abstention over speculative answering.
3. Collect user feedback as a secondary signal for continuous improvement.

### What Not To Do First

Do not start with:

- full RLHF style retraining
- satisfaction-only thumbs-up/down loops as the main fix
- more aggressive retrieval to "find something anyway"

Those are slower, noisier, and do not solve the online failure immediately.

## Recommended Product Behavior

Every incoming question should go through a 3-way decision:

- `answer`
- `clarify`
- `abstain`

### `answer`

Use when:

- top evidence is strong and specific
- retrieved evidence matches the entities in the question
- evidence coverage is sufficient
- no major contradiction or ambiguity signal is detected

### `clarify`

Use when:

- multiple plausible entities or documents match
- the question is underspecified
- the user likely asked with the wrong scope
- evidence exists, but it supports more than one interpretation

Example response:

- "질문이 어느 문서를 가리키는지 불분명합니다. `A.md`와 `B.md` 중 어느 쪽을 말씀하시는지 알려주세요."

### `abstain`

Use when:

- retrieval quality is weak
- evidence does not support the premise
- entity match is poor
- post-check detects unsupported or internally inconsistent claims

Example response:

- "현재 검색된 근거만으로는 질문의 전제를 확인할 수 없습니다. 질문의 대상 문서나 정확한 항목명을 더 알려주시면 다시 확인하겠습니다."

## Concrete Design For JARVIS

### 1. Add an `AnswerabilityGate`

Create a small decision layer between retrieval and generation.

Suggested output:

- `decision`: `answer | clarify | abstain`
- `reason_code`
- `confidence`
- `details`

Suggested input features:

- top-1 relevance score
- top-1 vs top-2 margin
- average relevance of top-k
- query term coverage in top evidence
- named entity / identifier overlap
- file or document scope match
- presence of conflicting evidence
- current planner confidence
- current citation verification warnings
- ambiguity markers from planner

### 2. Add explicit ambiguity detection

Extend the planner or a new detector to flag:

- multiple entity candidates
- multiple file candidates
- vague referents
- temporal ambiguity
- wrong-premise suspicion

This detector should produce:

- `is_ambiguous`
- `ambiguity_type`
- `candidate_targets`

### 3. Tighten the prompt

Change generation policy from:

- "ignore irrelevant evidence and answer from your own knowledge"

to:

- "if evidence does not support the answer, do not answer; explain the missing support"

For this product, unsupported parametric answering is usually worse than a refusal.

### 4. Promote verification from post-check to policy signal

Current citation verification should feed back into the decision process.

If verification warnings exceed a threshold:

- convert final behavior to `abstain`, or
- downgrade to `clarify`

For streaming:

- avoid showing the final answer as complete before minimal verification finishes
- or mark it as provisional until verification completes

### 5. Add entity-consistency checks

Add a lightweight entity or identifier consistency check over:

- user question
- top evidence chunks
- draft answer

This is specifically to catch:

- wrong person
- wrong file
- wrong table row
- mixed entities in one answer

### 6. Add structured user feedback, but keep it simple

Collect explicit feedback after the answer:

- `helpful`
- `wrong_answer`
- `wrong_document`
- `wrong_entity`
- `should_have_asked_clarification`
- `insufficient_evidence`

Optional free text can be added, but the main learning signal should be structured labels first.

Store alongside:

- query
- planner output
- retrieval candidates
- selected evidence
- final decision
- answer text

## Why Feedback Is Secondary, Not Primary

Feedback collection is still worth doing, but mostly for:

- failure clustering
- threshold tuning
- calibrator training
- regression fixtures

Reasons not to make it the first-line fix:

- user feedback is sparse
- users often skip feedback
- implicit feedback is noisy
- bad answers still happen before the model learns

So the order should be:

1. online gating and clarification
2. feedback logging
3. offline calibration and training

## Phased Execution Plan

### Phase 1: Immediate hardening

Low engineering cost, high impact.

- Raise the effective evidence threshold for answer generation.
- Block answers when top evidence quality is too weak.
- Remove prompt permission to answer from unsupported parametric knowledge.
- If verification warnings exist, return abstain-style copy instead of the generated answer for high-risk cases.

### Phase 2: Clarification-first flow

- Add ambiguity detection.
- Add clarification question templates.
- Surface candidate document or entity choices in menu bar UI.

### Phase 3: Train a calibrator

- Build a labeled dataset from:
  - regression failures
  - structured user feedback
  - manually reviewed traces
- Train a lightweight calibrator that predicts `answer / clarify / abstain`.

Possible model choices:

- logistic regression or XGBoost over engineered features
- later, a small local classifier if needed

### Phase 4: Continuous improvement loop

- review weekly failure samples
- update thresholds
- add regression tests
- periodically refresh the calibrator

## Success Metrics

Track these instead of raw answer rate alone:

- unsupported-answer rate
- user-corrected answer rate
- abstain precision
- clarification resolution rate
- answer-after-clarification accuracy
- fraction of answers later marked `wrong_document` or `wrong_entity`

The goal is not maximizing answer volume. The goal is maximizing trusted answers.

## Final Recommendation

For JARVIS, the best next move is:

- first: implement a pre-generation `answer / clarify / abstain` gate
- second: tighten the prompt and connect verification to refusal
- third: collect structured feedback for offline improvement

In other words:

- do not train the model first
- stop the wrong answer online first
- then use feedback to improve the gate over time

## Sources

- Rajpurkar, Jia, Liang. "Know What You Don't Know: Unanswerable Questions for SQuAD." arXiv, 2018. https://arxiv.org/abs/1806.03822
- Kamath, Jia, Liang. "Selective Question Answering under Domain Shift." ACL 2020. https://aclanthology.org/2020.acl-main.503/
- Asai et al. "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection." arXiv, 2023. https://arxiv.org/abs/2310.11511
- Yan et al. "Corrective Retrieval Augmented Generation." arXiv, 2024. https://arxiv.org/abs/2401.15884
- Min et al. "AmbigQA: Answering Ambiguous Open-domain Questions." EMNLP 2020. https://aclanthology.org/2020.emnlp-main.466/
- Lee et al. "Asking Clarification Questions to Handle Ambiguity in Open-Domain QA." Findings of EMNLP 2023. https://aclanthology.org/2023.findings-emnlp.772/
- Gao et al. "Continually Improving Extractive QA via Human Feedback." EMNLP 2023. https://aclanthology.org/2023.emnlp-main.27/
- Liu, Zhang, Choi. "User Feedback in Human-LLM Dialogues: A Lens to Understand Users But Noisy as a Learning Signal." EMNLP 2025. https://aclanthology.org/2025.emnlp-main.133/
- Chiang, Lee. "Merging Facts, Crafting Fallacies: Evaluating the Contradictory Nature of Aggregated Factual Claims in Long-Form Generations." Findings of ACL 2024. https://aclanthology.org/2024.findings-acl.160/
