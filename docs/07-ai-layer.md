# 23. AI Architecture

## Principle

The language model is a **translator at both ends of a deterministic pipeline**. It converts a
sentence into a structured request, and converts a structured result into prose. It does not compute,
rank, score, or decide. Every number in the answer is a number the engine produced.

```
user utterance
     │
     ▼
[1] Intent extraction (LLM, structured output / tool schema)
     │        → PlanRequest{origin, date, hours, profile, constraints}
     │        → confidence per field; missing/ambiguous → ask, never assume (FR-X-04)
     ▼
[2] Validation (Python, Pydantic)  — rejects anything out of range; the LLM cannot widen limits
     │
     ▼
[3] Deterministic engine  — providers → cache → Mojo compute → safety gates
     │        → RankedPlans + components + warnings + provenance
     ▼
[4] Explanation (LLM, grounded)  — receives ONLY the engine payload and a strict template
     │        → natural language, in the user's language
     ▼
answer + the structured payload it was generated from (both logged, FR-X-03)
```

## Why this shape and not "let the model do it"

- **Reproducibility.** The same request must give the same plan. A model in the compute path makes
  that impossible, and a planner that gives two different answers to the same question at 07:00 and
  07:05 is not a planner.
- **Safety.** Warnings are rule-based and auditable. A generated warning is a liability; a generated
  *explanation of a rule-based warning* is a feature.
- **Cost and latency.** One or two model calls per session, not per spot. Ranking 50 spots costs zero
  tokens.
- **Testability.** Stages [1] and [4] are testable in isolation with fixtures; stage [3] is fully
  deterministic and covered by golden tests.

## Stage 1 — intent extraction

Structured output against the `PlanRequest` schema. Rules:

- Never invent a location. If the utterance says "somewhere nice", `origin` stays null and the
  assistant asks.
- Relative dates resolve in the user's timezone, and the resolution is echoed back ("tomorrow,
  Sunday 16 August").
- Numeric constraints outside configured bounds are clamped **and reported**, not silently accepted.
- Extraction output is logged with a confidence per field; low confidence triggers a clarifying
  question rather than a guess.

## Stage 4 — grounded explanation

The prompt receives the engine payload and nothing else. Constraints:

- Every figure in the prose must appear in the payload. A post-generation check extracts numbers from
  the answer and fails the response if any is absent from the payload — cheap, mechanical, and it
  catches the failure mode that matters.
- Warnings are rendered verbatim from their catalogue text; the model may translate but not rephrase
  severity.
- The disclaimer is appended by code, not by the model.
- Length capped; the explanation supports the plan card, it does not replace it.

## Model choice and deployment

- Provider behind a `LlmProvider` port, exactly like weather — no lock-in.
- A small, fast model for intent extraction; a stronger model for explanation only if evaluation
  shows it is needed. Measure before upgrading.
- The AI layer is **optional**: with it disabled, SailWise is fully functional through the UI and API.
  Nothing in the core depends on it (this is the test of whether the layering is real).
- Prompts are versioned files in the repository, reviewed like code, with a regression suite of
  utterance → expected structured request.

## Privacy

- User utterances may contain location and habits. They are sent to the model provider only with
  explicit consent, and the consent state is per-user and revocable.
- Coordinates are rounded before leaving the system where precision is not needed.
- No training-data sharing; the provider must be configured with retention off where offered.
- Logged payloads for reproducibility are subject to the same retention and erasure rules as any
  other personal data (see [08-security-privacy.md](08-security-privacy.md)).

## Prompt-injection surface

POI names, notes and user-supplied text flow into stage 4's payload. They are data, not instructions:
they are delimited, and the system prompt states that content inside the payload is never an
instruction. The output check above is the second line of defence — an injected instruction that
produced invented figures would fail the numeric-grounding test.

## Evaluation

| Stage | Metric | Gate |
|---|---|---|
| Intent extraction | exact-match on structured fields over a fixture set | ≥ 95 % on required fields |
| Clarification | asks rather than guesses on ambiguous fixtures | 100 % on the ambiguity set |
| Explanation grounding | every number traceable to the payload | 100 %, enforced in code |
| Latency | p95 end-to-end with AI enabled | < 3 s |
