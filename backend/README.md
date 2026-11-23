# Adaptive Viva Generator: Backend API

FastAPI service that connects the **AST engine** (`adaptive_viva_ast/`, Subhadeep) to the
**Next.js frontend** (`../frontend`, Kaushik). It handles auth and RBAC, courses and TAs, uploads,
background analysis, LLM viva-question generation, review/approval and PDF/CSV export.

```
backend/
├── adaptive_viva_ast/      # AST engine (unchanged; imported as a library)
├── app/
│   ├── main.py             # FastAPI app, CORS, /health
│   ├── config.py           # all settings (env vars)
│   ├── db.py / models.py   # SQLAlchemy 2.0 tables
│   ├── schemas.py          # request/response bodies (match frontend/lib/types.ts)
│   ├── security.py         # bcrypt + JWT
│   ├── deps.py             # current user, course access checks, BR-1/BR-2
│   ├── errors.py           # {"error": {"code", "message"}} body
│   ├── queue.py            # Redis/RQ or inline background jobs
│   ├── pipeline.py         # job: analyse -> generate -> DRAFT
│   ├── routers/            # auth, courses, assignments, submissions, questions
│   └── services/
│       ├── analysis.py     # adapter over the AST engine: findings + question targets
│       ├── questions.py    # LiteLLM + Instructor generator, template fallback
│       ├── uploads.py      # .py / .zip handling
│       └── export.py       # PDF (reportlab) / CSV
├── tests/                  # pytest (27 tests)
├── Dockerfile, docker-compose.yml, .env.example
```

## Run locally (no Docker, no Redis, no API key)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

* Swagger docs: http://localhost:8000/docs
* Frontend: in `frontend/.env.local` set `NEXT_PUBLIC_MOCK=false`, then `npm run dev`.
  `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` is already correct.

With `LLM_MODEL` empty, questions come from built-in templates, which is enough for the demo.
To use a real LLM, set for example `LLM_MODEL=gemini/gemini-1.5-flash` and `GEMINI_API_KEY=...`
(any LiteLLM model works; use `LLM_MODE=json` for models without function calling).

## Run the full stack (PostgreSQL + Redis + worker)

```bash
cd backend
docker compose up --build              # api on :8000
docker compose up --scale worker=3     # more analysis workers
```

## Tests

```bash
python -m pytest
```
CI runs on GitHub Actions (`.github/workflows/backend-ci.yml`): pytest, then a Docker build.

## API (`/api/v1`)

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/auth/register` | anyone | create instructor account (or claim a TA invite) |
| POST | `/auth/login` | anyone | sets httpOnly JWT cookie, returns `{user}` |
| POST | `/auth/logout` · GET `/auth/me` | user | |
| GET/POST | `/courses` | member / instructor | list my courses / create |
| GET/PATCH/DELETE | `/courses/{id}` | member / instructor | |
| GET/POST | `/courses/{id}/members` | member / instructor | list / add TA by email |
| PATCH/DELETE | `/courses/{id}/members/{user_id}` | instructor | grant approve right (BR-2) / remove |
| GET/POST | `/courses/{id}/assignments` | member / instructor | |
| GET/PATCH/DELETE | `/assignments/{id}` | member / instructor | |
| GET | `/assignments/{id}/submissions` | member | list with status |
| POST | `/assignments/{id}/submissions` | member | multipart `file` (.py/.zip) + `student_ref` -> 202 `{job_id}` |
| GET | `/submissions/{id}` | member | code + findings + questions |
| POST | `/submissions/{id}/approve` | instructor (BR-1) | lock set |
| POST | `/submissions/{id}/reanalyse` | member | re-run a failed/draft submission |
| GET | `/submissions/{id}/export?format=pdf\|csv` | member | approved sets only |
| DELETE | `/submissions/{id}` | instructor | |
| PATCH | `/questions/{id}` | member | `{question_text}` edit or `{state: DISCARDED\|DRAFT}` |
| POST | `/questions/{id}/regenerate` | member | new question for that one finding |
| GET | `/health` | | db / queue / llm status |

Errors always look like `{"error": {"code": "LOCKED", "message": "..."}}`.

**Submission status:** `UPLOADED → ANALYSING → GENERATING → DRAFT → APPROVED`, or `PARSE_FAILED` / `FAILED`.

**Zip layout:** `ROLL.py` or `ROLL/*.py` (one wrapping folder is fine). A student's multiple files are
joined into one, separated by `# ===== file: name =====` headers.

## How question generation works

1. `services/analysis.py` runs the AST engine and keeps the notable results: recursion (noting
   whether it's memoised), nested loops, deep nesting (outermost only), high complexity, long
   functions, while-vs-for, and dict/set choices. Each one has lines, node type and a reason (FR-4.3.4).
2. The most interesting findings become question targets, up to `num_questions` (default 5).
   If there are fewer than 3, general comprehension targets are added on the biggest functions,
   or on the module itself (FR-4.6.2).
3. `services/questions.py` sends **only** these insights plus short flagged snippets to the LLM,
   never the whole file (FR-4.4.1, NFR-5.3.5). Instructor validates the reply against a
   Pydantic schema built for *these* targets: one question per target, and `related_line` must
   fall inside the target's lines (BR-3). Invalid replies are retried automatically (FR-4.4.4).
   If the LLM is off or keeps failing, the template generator is used, so the demo never breaks.

## SRS traceability

| Requirement | Where |
|---|---|
| FR-4.1.1 register/login | `routers/auth.py` |
| FR-4.1.2 course CRUD | `routers/courses.py` |
| FR-4.1.3 assignments + language/rubric | `routers/courses.py`, `routers/assignments.py` |
| FR-4.1.4 TAs, restricted rights | `routers/courses.py` members, `deps.py` |
| FR-4.2.1/2 single + zip upload | `routers/assignments.py`, `services/uploads.py` |
| FR-4.2.3 5 MB limit (configurable) | `config.max_file_bytes` |
| FR-4.2.4 syntax check before analysis | `services/analysis.syntax_check` |
| FR-4.3.x AST analysis | `adaptive_viva_ast` + `services/analysis.py` |
| FR-4.4.x LLM questions, schema, retry, count | `services/questions.py`, `pipeline.py` |
| FR-4.5.3/4/5 edit / regenerate one / discard | `routers/questions.py` |
| FR-4.5.6 approve | `routers/submissions.py` |
| FR-4.6.1 syntax error with line | status `PARSE_FAILED` + `error` |
| FR-4.6.2 fallback general questions | `analysis.pick_targets` |
| FR-4.7.1 PDF/CSV export | `services/export.py` |
| FR-4.7.2 history | submissions/findings/questions + raw `analysis` JSON kept in DB |
| NFR-5.1.2 async batch | `queue.py` (Redis + RQ worker) |
| NFR-5.3.1 encryption at rest | `models.EncryptedText` (Fernet, `ENCRYPTION_KEY`) |
| NFR-5.3.2/3 access control, RBAC | `deps.py` |
| NFR-5.3.4 bcrypt | `security.py` |
| NFR-5.3.5 minimal code to LLM | snippets only, `LLM_SEND_SNIPPETS` |
| BR-1/BR-2 approval rights | `deps.can_approve` |
| BR-3 traceable questions | schema validator + `related_line` always set |
| 2.5 Docker + GitHub Actions + pytest | `Dockerfile`, `docker-compose.yml`, `.github/workflows` |

## Known limits (MVP)

* Python only (as in the SRS); the analysis adapter is the place to add tree-sitter languages.
* Tables are created at startup (`create_all`). Add Alembic migrations before a real production deploy.
* Single-file uploads are capped at 5 MB and zips at 50 MB (configurable).
