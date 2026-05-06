# Testing Matrix

## Why this is needed

The project currently had many ad-hoc test scripts, but not a stable regression suite. That is risky for this codebase because:

- many flows are cross-role: admin -> teacher -> student
- several features depend on DB side effects
- agent behavior is routed by heuristics and follow-up context
- Groq / external LLM calls can fail, timeout, or return malformed data

The new automated suite in `tests/` covers the highest-risk backend paths. This file lists the broader regression matrix so future work can keep expanding coverage.

## Automated coverage added now

- Auth:
  - student register
  - login creates login session
  - login refresh triggers planning regeneration
- Admin:
  - create teacher account
  - list non-admin users
- Subject / classroom:
  - teacher subject CRUD
  - classroom creation
  - student cannot join 2 classes of the same subject
- Planning agent:
  - regenerate active plan from visible documents and scores
  - chat adjustment reorders steps
- Orbit agent:
  - document-followup request uses opened document context
  - recommendation flow returns `open_document` action metadata
  - teacher directive is persisted
- Nova / teacher agent:
  - pending follow-up is preserved across turns
  - exam intent routes to the exam tab
- Question bank:
  - append 10 questions
  - append again without corrupting old rows
  - manual add / update / delete
- Assessment:
  - generate session quiz and persist generated questions
  - submit quiz and persist score history + document evaluation
  - fallback still generates questions when LLM batch generation fails

## Admin regression checklist

- Create teacher account:
  - valid teacher account is created
  - random password is returned exactly once
  - duplicate email is rejected
- Create student account:
  - valid student account is created
  - duplicate email is rejected
- Delete user:
  - teacher can be deleted
  - student can be deleted
  - admin account cannot be deleted
- User listing:
  - admin users are excluded from list
  - total count matches returned rows
- Subject management:
  - create subject
  - rename subject
  - subject rename syncs deprecated subject string fields
  - delete subject blocked if classrooms still exist

## Teacher regression checklist

- Classroom management:
  - create class with valid subject
  - edit class name
  - delete class removes enrollments and class documents
  - teacher cannot update/delete another teacher's class
- Document management:
  - upload document
  - list by class
  - list by subject
  - preview/view/download visible document
  - hidden document is not accessible to students
  - delete document removes DB row, chunks, and physical file when present
- Question bank:
  - generate full bank from document
  - append 10 more questions
  - generated count equals saved count
  - repeated append does not overwrite previous rows unexpectedly
  - manual add/update/delete works
  - malformed options are rejected
- Exam generation:
  - export Word exam for a class with documents
  - multiple exam versions are created
  - MCQ answer key exists for each version
  - fallback still exports when Groq is unavailable
- Nova / teacher agent:
  - class overview request routes correctly
  - material request opens documents tab
  - exam generation request asks follow-up when fields are missing
  - next turn can complete the pending request
  - orbit directive creation persists notification + directive

## Student regression checklist

- Auth:
  - register student with unique `student_id`
  - login creates / updates progress row
  - logout closes open login sessions
- Join class:
  - valid class code joins successfully
  - duplicate join is rejected
  - second class of same subject is rejected
- Library:
  - student only sees visible documents from enrolled classes
  - preview works
  - download works
  - hidden document returns 403
- Assessment:
  - baseline generation returns available pre-generated questions
  - session quiz generation persists questions
  - submit saves `AssessmentHistory`
  - submit saves `StudentDocumentEvaluation`
  - submit saves `StudentDocumentScoreHistory`
  - session pass/fail threshold behaves correctly
  - roadmap session unlock logic behaves correctly
- Evaluation:
  - score history endpoint returns chronological entries
  - roadmap endpoint returns progress percent

## Agent-specific regression checklist

### Nova / Teacher Agent

- intent classification:
  - course info
  - class overview
  - class analytics
  - student info
  - material
  - exam generation
- follow-up memory:
  - missing-info prompt sets pending request
  - next message reuses pending context
  - stale pending request can be cleared
- failure mode:
  - LLM classify path errors out -> rule-based fallback still returns a usable response
  - slow LLM classify path times out -> fallback still returns a usable response

### Orbit Agent

- entry message builds onboarding reply
- progress overview branch persists chat history
- open-document request returns recommendation payload and `open_document` action
- document-followup request with `document_id` uses opened document context
- document-followup request can recover document from recent history
- teacher directive endpoint persists weekly directive
- non-student account is blocked from Orbit progress/history

### Planning Agent

- active plan uses only visible documents from enrolled classes
- low-score docs are prioritized before no-score docs
- manual refresh archives previous active plan and creates a new one
- chat adjustment:
  - prioritize subject earlier
  - defer subject later
  - add extra load for today
  - add extra load for this week

### Assessment Agent

- if question bank already exists, student quiz generation reads from DB only
- pre-generate for document can replace old rows
- append generation can extend instead of replace
- if Groq / LLM generation fails, local fallback still returns enough questions
- generated options must be 4 choices and 1 correct answer

## Failure and resilience tests to keep adding

- Groq returns `401 Unauthorized`
- Groq times out
- Groq returns malformed JSON
- vector store unavailable
- SQLite locked / busy timeout paths
- duplicate question generation under concurrent append requests
- large document question generation under repeated retries
- teacher agent high-latency request does not hang the request forever

## Performance guardrails

These should become executable checks later:

- Orbit `/chat`: normal response under 3s for non-LLM routing branches
- Nova `/nova-interactive`: non-LLM fallback under 2s
- append 10 questions: no request should block indefinitely
- assessment submit: completes and commits within a bounded time without DB deadlock

## Run the suite

After installing backend test dependencies:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests -q
```
