# CSC — Fresh Eyes Briefing
> This document is written for a reviewer with no prior context on this project.
> The goal is to get honest perspective on design decisions and failure patterns
> before writing more code. Please challenge assumptions freely.

---

## What Is This?

A natural-language camp search assistant for a Canadian camp directory (camps.ca).
Parents type queries like *"hockey camps in Toronto for my 10-year-old"* and get
ranked results from a MySQL database of ~1,300 camps.

Built with: Streamlit (UI) + MySQL (camp data) + Claude AI (three call sites).

---

## How It Works (Pipeline)

Each user message goes through this chain:

```
1. Fuzzy Preprocessor     keyword matching → tag hints (no API)
2. Intent Parser          Claude Haiku → structured JSON (tags, city, age, etc.)
3. Session Merge          accumulate params across conversation turns
4. CSSL                   MySQL query → result pool
5. Decision Matrix        ICS × RCS score routing
6. Reranker               Claude Haiku → reorder + write blurbs
7. Concierge Response     Claude Sonnet → 2-3 sentence narrative + follow-up
```

The system is **stateful** — it remembers the conversation and merges new intent
with previous search parameters (e.g. "now show me overnight" keeps the activity
and location from the prior turn).

---

## The Three Claude Call Sites

| Role | Model | What it does |
|---|---|---|
| Intent Parser | Haiku 4.5 | Extracts structured params from free text → JSON |
| Reranker | Haiku 4.5 | Re-scores and annotates results for relevance |
| Concierge | Sonnet 4.6 | Writes the conversational response the user sees |

---

## Observed Failure Patterns

These are real failures found during testing. Some have been patched; others expose
deeper design questions.

### 1. Concierge Hallucinated a Factual Claim
**What happened:** User asked about all-girls camps. Camp Wenonah appeared in results
(incorrectly — it's coed). User asked the concierge "is Camp Wenonah all-girls?"
The concierge confirmed it was all-girls with confidence.

**Root cause:** The concierge only sees the top results passed to it. It has no
access to ground-truth camp data. When asked to confirm a factual claim, it
sycophantically agreed with the user's framing.

**Question for fresh eyes:** How should a system like this handle direct factual
questions about specific camps? Should the concierge be allowed to answer them at all?

---

### 2. Province-Wide Loop
**What happened:** User searched "skateboarding camps in Etobicoke." No results.
System offered to search province-wide. User said "yes." System searched again —
still no results. Offered province-wide again. Infinite loop.

**Root cause:** The geo-broadening logic cleared the `city` field but not `lat`,
`lon`, `radius_km`. The MySQL query still filtered by proximity to Etobicoke.

**Question for fresh eyes:** Is accumulating geographic state across turns the
right design? Should each turn start fresh with location, or is accumulation
genuinely useful?

---

### 3. Gender Filter Misapplication
**What happened:** User searched "skateboarding camps for my 10-year-old boy."
The intent parser set `gender=Boys`. This filtered out Leaside Volleyball Club
(a valid Toronto camp) because its `gender` field was NULL in the database.

**Root cause:** Two separate problems:
- The intent parser treated "my son/boy" as a request for a boys-only camp
- The DB has sparse gender data — most programs have `gender=NULL` (unknown), not `gender=0` (coed)

**Patch applied:** Intent parser now only sets gender when the user explicitly asks
for a gender-segregated camp ("all-girls camp", "boys only"). "My son/daughter" → null.

**Question for fresh eyes:** Is gender filtering via a single `programs.gender`
field even viable given sparse data? What's the right way to handle this?

---

### 4. Concierge Generated a Dead-End Loop
**What happened:** After showing province-wide results, user said "narrow to
surrounding cities." Concierge responded with: *"It looks like results are pulling
from Oakville — to truly narrow, try removing Oakville and focusing on Toronto,
Mississauga, Burlington, or Milton. Which works best for your family?"*

User answered. That answer became a new query. The loop continued.

**Root cause:** The concierge added a city-picker follow-up question when results
were already displayed. The follow-up question looked like a useful suggestion but
created an irresolvable loop.

**Question for fresh eyes:** Should a conversational AI layer (concierge) ever
direct the user to re-specify something when results are already on screen? What
are the rules for when a follow-up question is helpful vs. harmful?

---

### 5. "Surrounding Cities" Has No Meaning
**What happened:** After broadening to province-wide, the user said "narrow to
surrounding cities." The system has no memory of what the original city was
(it was cleared during the geo-broadening step), so "surrounding" has no referent.

**Question for fresh eyes:** Should the system preserve the original search
location even after broadening? How should "nearby" / "surrounding" be interpreted
without storing geographic history?

---

### 6. Affirmative Detection Was Too Narrow
**What happened:** After the province-wide suggestion, user said *"show me the
7 camps"*. System didn't recognise this as an affirmative response and re-ran
the LLM pipeline as a new query. The new query produced a different (wrong) result.

**Patch applied:** Added `startswith("show")` as an affirmative match.

**Question for fresh eyes:** Is regex/keyword affirmative detection the right
approach, or should this go back through the intent parser with a "pending
suggestion" flag in context?

---

## Deeper Design Questions

These haven't been "fixed" — they're open architectural questions.

**Q1: Should the concierge be able to answer questions about specific camps?**
Currently the concierge only sees the top 3 results as context. If a user asks
a factual question ("Is this camp coed?", "How much does it cost?"), the concierge
either hallucinates or gives a vague non-answer. Should this be a separate lookup
path?

**Q2: Is accumulated session state a feature or a source of bugs?**
Every search turn merges new intent with old. This lets users say "now show me
overnight" and keep the previous location. But it also causes stale params to
bleed into unrelated searches. Most of the bugs above come from stale state.
Is the UX benefit worth the complexity?

**Q3: Is the intent parser the right place to handle all disambiguation?**
Currently the intent parser (an LLM call) handles: activity extraction, location,
age, gender, dates, language, and affirmative detection. Is this one call doing
too many jobs? What should be split out?

**Q4: Three separate LLM calls per turn — is that the right structure?**
Intent (Haiku) → Rerank (Haiku) → Concierge (Sonnet). Each adds latency and cost.
Are all three necessary? Could any be combined or replaced?

**Q5: The concierge's follow-up question is uncontrolled.**
The concierge is instructed to end with "ONE natural follow-up offer." In practice
these follow-ups sometimes create loops (see failure 4). Should follow-up questions
be templated/constrained rather than LLM-generated?

---

## What's Working Well
- Basic search (activity + location + age) is reliable
- Multilingual queries work correctly
- Gold/silver/bronze tier ranking is meaningful to users
- Session refinement ("now add overnight") works most of the time
- Surprise Me (bypasses LLM entirely, direct SQL) is stable

---

## What to Ask Your Fresh Eyes Reviewer

1. Looking at the failure patterns — do you see a common root cause?
2. For the concierge hallucination problem specifically — what guardrails would you add?
3. Is stateful session accumulation worth the complexity for this use case?
4. How would you redesign affirmative detection?
5. What's missing from this system that would make results more trustworthy?
