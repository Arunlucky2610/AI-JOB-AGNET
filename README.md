# Orbit — AI job application workspace

A local first implementation of the agreed product. **There is no login page.** The app opens personal onboarding immediately. Dashboard access follows profile completion and confirmation.

**Scope: LinkedIn only.** Employer career pages (Greenhouse, Lever, Ashby, Workday, JobSpy, company portals) and Naukri were removed; the old code is archived in `archive/removed-career-portal-code/` (a zip of the code before the change is in `archive/`). Indeed was removed too: its bot detection signed out every new cloud browser, so each run needed a fresh manual sign-in. Its code and tests are in `archive/removed-indeed-code/`.

## Run locally

Requires Node 22+ and Python 3.11+.

Clone with the `vendor/career-ops` submodule: `git clone --recurse-submodules https://github.com/saivarshith6/job-agent.git` (or run `git submodule update --init` in an existing clone). `.env` is committed in this private repo, so skip the `Copy-Item` line below.

```powershell
npm install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env  # Only on a fresh setup; do not overwrite existing keys.
.\start.ps1
```

Open http://127.0.0.1:3000. The current workspace already has its dependencies installed and private local configuration prepared. `start.ps1` starts FastAPI in a hidden child process and Next.js in the current terminal. Stop with Ctrl+C. API documentation is at http://127.0.0.1:8000/docs. Browser mutations use the configured Origin header.

## Implemented

- Next.js/React interface: overview, application tracker, live agent (large Live View with full screen), five-step onboarding including **Career stage** (Intern / Fresher / Experienced), preferences.
- Persistent local workspaces backed by HttpOnly session cookies.
- Resume text extraction from PDF, DOCX and TXT (5 MB limit), profile confirmation, preferences, skills, experience, authorization, sponsorship and screening answers.
- **LinkedIn agent** (`backend/platform_agent.py`, `backend/linkedin.py`): profile-driven Easy Apply searches, one-by-one review, DeepSeek fit scoring (fresher mode needs at least 40%), tailored resume and cover letter, and Easy Apply form filling and submission in the browser, including LinkedIn's shadow-DOM dialog. Confirmed submission evidence is required for "Applied".
- Saved logins: each user gets a Browserbase browser profile so sign-in persists between runs; sign-in, verification and CAPTCHA always pause for the person in Live View.
- **Connect your accounts gate**: on the Live agent page, Start agent stays disabled until the person has signed in to LinkedIn (`/api/connections/<platform>/check`, embedded Live View to sign in); once confirmed, Browserbase's saved profile keeps them signed in so this is not asked again unless a saved session actually expires.
- Deterministic prefilters before any model call (senior or non-tech titles), Jev triage, deduplication by canonical vacancy URL, daily limit, pacing between jobs.
- Rules-first form planning: routine Easy Apply steps (known contact field, document upload, prefilled controls, one way forward) are planned with no model call; only questions and unknown controls go to the model.
- Individual approval, batch approval, and explicitly enabled automatic mode. Approved packages carry exact-package hashes; edits invalidate approval.
- Ambiguous submissions enter `needs_verification` and are never retried automatically. Restart recovery pauses interrupted work.
- SSE refresh notifications and persisted activity events. Demo mode simulates an application and never contacts a job site.

## Not built yet
- Production items: durable job queue, PostgreSQL migrations, per-user rate limits, encrypted browser-context storage, monitoring, account recovery.

## Connections

Set secrets only in `.env` or the deployment secret store. Never use `NEXT_PUBLIC_` for API keys.

```dotenv
OPENROUTER_API_KEY=
BROWSERBASE_API_KEY=
```

Two models, both through OpenRouter:

- **DeepSeek** (`deepseek/deepseek-v4-flash-0731`) writes the resume and cover letter, does the deep fit review, plans unusual form steps, and is the fallback for everything else.
- **Jev** (`typesafe/jev-1.13`, TypeSafe's fast decision model) does read-only job triage in under a second. It asks small yes/no and pick-one questions, numbers are compared in code, and anything it is unsure about or any error goes to DeepSeek. It never authorizes a submission and never sees personal data, only the public job text.

`JEV_MODE` in `.env`: `shadow` (default; Jev's verdict is logged and compared with DeepSeek but not acted on), `active` (confident skips are acted on, saving a DeepSeek call each), or `off`. The run state records how often Jev agreed with DeepSeek (`jev` counters), so switch to `active` only after it has matched DeepSeek on real jobs. Browserbase provides the cloud browser, Live View and saved login profiles. Browserbase minutes are used while a session is open, including while waiting for you to sign in.

## Database

The local preview uses SQLite. The SQLAlchemy schema also targets PostgreSQL (see `docker-compose.yml`); set `DATABASE_URL` and restart. Existing SQLite data is not migrated automatically.

## Verification

```powershell
npx tsc --noEmit
.\.venv\Scripts\python.exe -m unittest backend.test_api backend.test_batch backend.test_worker backend.test_linkedin backend.test_scope backend.test_connections -v
```

Tests use isolated temporary databases and no external LinkedIn, Browserbase or OpenRouter calls. Browser tests drive the real worker and platform agent in local Chromium against a LinkedIn-shaped fake site (LinkedIn's dialog is inside a shadow root).

## Structure

`app/` interface. `backend/main.py` API. `backend/agent.py` run control. `backend/platform_agent.py` dispatches to `backend/linkedin.py`. `backend/worker.py` controlled browser form execution. `backend/services.py` model and browser connectors. `backend/domain.py` matching rules and career stage. `backend/career_ops*.py` fit evaluation and document rendering. `backend/db.py` persistence.

## Important notes

- Automating LinkedIn breaks its terms of use, and accounts that apply in bulk can be restricted. Keep the daily limit low.
- This is a single-process pilot. Run one backend process.
