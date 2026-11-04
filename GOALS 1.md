# Orbit — Master System Goals & Technical Charter

## 1. Mission

**Apply to fewer, better jobs.** Orbit is not a mass-apply bot. It discovers high-conviction job opportunities that genuinely fit the candidate, verifies live on employer portals that vacancies are actively open, synthesizes tailored resumes and cover letters for each specific role with zero fabrication, and submits only what the candidate has reviewed and cryptographically authorized. A few verified, highly-tailored applications beat hundreds of generic, automated submissions.

---

## 2. Quality Over Quantity (Core Principles)

| Instead of… | Orbit does… |
| :--- | :--- |
| Applying blindly to everything a search returns | Applying only to vacancies that pass deterministic pre-filtering, active status validation, and deep LLM fit review against the candidate's confirmed profile. |
| Trusting stale search snippets and expired listings | Reading every job live on its LinkedIn page and skipping closed or no-longer-accepting listings. |
| One generic résumé for every submission | Synthesizing a tailored résumé and role-specific cover letter per vacancy, citing verified candidate evidence with **zero hallucinated qualifications**. |
| Guessing answers to screening questions | Mapping answers strictly from confirmed profile facts; any ambiguous or unknown question is escalated to the candidate. |
| Spraying submissions without review | Stopping before submission: presenting the candidate with tailored documents, form fields, and screenshot preview, requiring one-click authorization. |
| Counting "sent" without evidence | Marking **Submitted** only upon receipt of official employer confirmation (receipt banner, requisition ID, confirmation email); ambiguous submissions enter `needs_verification`. |
| Abandoning the application after submission | **Tracking the post-submission lifecycle**: recording recruiter responses (`shortlisted`, `assessment`, `interview`, `offer`, `rejected`), user fit feedback (👍/👎), and dynamic shortlist conversion analytics. |

---

## 3. What Makes a Job a Quality Match

An opportunity enters the candidate's pipeline only when all five criteria are satisfied:
1. **It is actively open now (PRD FR-1):** The ATS or portal lists it, no application deadline has expired, no closure notice exists, and the application form is active.
2. **The role fits (PRD FR-2):** Title, department, and core responsibilities semantically align with the candidate's target roles and career level (Intern / Fresher / Experienced).
3. **The requirements fit (PRD FR-3):** Stated minimum professional experience is within candidate range. Required skills are verified; gaps are transparently highlighted.
4. **The constraints fit (PRD FR-5):** Geographic location, work arrangement (Remote / Hybrid / Onsite), visa sponsorship requirements, and work authorization align with candidate settings. Companies on the candidate's blacklist are excluded.
5. **The fit score clears the threshold (PRD FR-4):** Candidate match score meets or exceeds the user-configured minimum (default: 60% for freshers, 70% for experienced).

*Fields the employer did not state (salary, exact tenure, bonus) are marked **"Not stated"**, never guessed.*

---

## 4. Scope: LinkedIn Easy Apply Only

Orbit applies on **LinkedIn (Easy Apply)** only. Employer ATS adapters (Greenhouse, Lever, Ashby, Workday, company portals), Naukri and Indeed were removed; their code is archived in `archive/`. Restoring them is a separate, future decision, not part of this charter.

| Capability | Status |
| :--- | :--- |
| LinkedIn Easy Apply search, review and submit | Built (Browserbase session, shadow-DOM dialog, human takeover for login/CAPTCHA) |
| Goal-driven fit judgment against the candidate's own target roles, level and constraints | Built; roles are the candidate's own, widened only in the direction they chose |
| Post-submission outcome tracking (`PUT /api/applications/{id}/outcome`, `GET /api/outcomes/summary`) | Built (API); stages, 👍/👎 fit feedback, shortlist conversion |
| Live "still open" verification | Built: each ranked job is re-opened on LinkedIn right before documents are written and again when the form opens; result is open, closed or uncertain, with evidence and time. Only "open" counts as verified. |
| Cross-posting deduplication | Built: same company, title and place under another URL is skipped (`entity_key`). |
| Agent loop, ranking, plan and decision trace | Built (`backend/orchestrator.py`, `platform_agent.ranked_applications`) |
| Grounded documents | Built: numbers, certifications and skills the candidate lacks are flagged and block approval until removed or confirmed |
| Submission evidence | Built: confirmation text, time, job id and screenshots (before submit, confirmation) |
| Outcome UI and conversion analytics | Built (Applications tab, `/api/outcomes/*`); advisory only, nothing learns automatically |

---

## 5. Discovery & Pacing

1. **Searches come from the candidate's goal**: their own target roles first, location and Easy Apply, experience level from career stage. Fresher mode widens roles only within what the candidate asked for (AI roles for AI-minded candidates, junior software roles for juniors in software/AI). A candidate targeting a non-tech role is never searched for AI Engineer jobs.
2. **Cheapest check first**: known jobs, senior/off-goal titles, years-of-experience text, Jev triage, then the DeepSeek fit review.
3. **Fewer, better**: fresher-mode fit floor is **60%** (`MIN_FIT`); the experienced default threshold is 70%. Below the floor the job is skipped, not applied to.
4. **Pacing & budget**: daily application quota (1-10, default 3), pauses between pages, per-run model spend cap (`RUN_BUDGET_USD`, default $1.00).

---

## 6. Non-Goals (Strict Guardrails)

- **No Mass Spray-and-Pray:** Orbit will never submit hundreds of unverified, generic applications.
- **No Unreviewed Submissions:** Autonomous execution prepares and autofills applications, but submission requires candidate review or explicitly authorized automatic mode with cryptographic package hashes (`approved_hash`).
- **No Fabrication:** The agent will never invent certifications, employers, skills, or metrics not supported by the candidate's confirmed resume.
- **No Unauthorized Credential Bypassing:** Orbit will never attempt to crack logins, bypass 2FA, or forge signatures. Authentication challenges are handed over to the candidate in Live View.
- **No Third-Party Aggregator Spam:** Primary focus remains direct employer ATS portals.

---

## 7. Production Tech Stack

### Frontend
| Component | Version | Role in Architecture |
| :--- | :--- | :--- |
| **Next.js** | 15.5+ (App Router) | Web application framework; handles proxy routing, server state, and page layout. |
| **React** | 19 | Interactive UI (Overview dashboard, Application Tracker, Custom link modal, Live View). |
| **TypeScript** | 5.9 | Full type safety across all frontend schemas and API contracts (`npx tsc --noEmit` = 0 errors). |
| **Tailwind CSS** | 3.4+ | Design token system, dark-theme dashboard, and responsive mobile/desktop layouts. |
| **Lucide React** | 0.468 | UI iconography. |

### Backend
| Component | Version | Role in Architecture |
| :--- | :--- | :--- |
| **Python** | 3.11+ | Backend runtime. |
| **FastAPI + Uvicorn** | 0.139 / 0.48 | High-performance asynchronous REST API and Server-Sent Events (SSE). |
| **SQLAlchemy** | 2.0+ | Object-relational mapping: Users, Jobs, Applications, Events, Platform Connections. |
| **SQLite / PostgreSQL** | 3 / 16+ (psycopg3) | Local development preview (`orbit.db`) and containerized production target (`docker-compose.yml`). |
| **httpx** | 0.28+ | High-throughput asynchronous HTTP client for ATS API ingestion and external service calls. |
| **Playwright** | 1.62+ | Headless Chromium automation over CDP for cloud browser navigation and form execution. |
| **PyPDF / ReportLab / Docx** | 6.12 / 4.5 / 1.2 | Local, secure document parsing and tailored PDF/DOCX generation (cross-platform on Windows and Linux). |

### External Cognitive & Automation Services
| Service | Provider | Role |
| :--- | :--- | :--- |
| **DeepSeek v4 Flash** | OpenRouter (`deepseek-v4-flash-0731`) | Full JD semantic matching, tailored resume/cover letter generation, and complex form step planning. |
| **TypeSafe Jev** | OpenRouter (`typesafe/jev-1.13`) | Optional, ultra-fast pre-triage classifier (`JEV_MODE=shadow\|active\|off`) for high-volume screening. |
| **Browserbase** | Cloud Infrastructure | Standardized, isolated cloud Chromium sessions with persistent profiles, residential proxies, and Live View streaming. |
| **Hybrid Web Search & Firecrawl** | Search APIs / Firecrawl v2 | Live career portal discovery and JS-rendered DOM extraction. |

---

## 8. Verification & Success Measures

Orbit's success is measured by candidate outcome quality, not arbitrary volume.

1. **Shortlist Conversion Rate (PRD FR-8):** The percentage of submitted applications that progress to recruiter screenings and interviews (tracked in the Application Tracker).
2. **Zero False Open (PRD FR-1):** Zero expired, canceled, or phantom requisitions admitted into the pipeline.
3. **Zero Fabrication:** 100% of claims in generated resumes and cover letters trace to confirmed candidate evidence.
4. **Zero Duplicate Submissions (PRD FR-11):** Cross-channel deduplication guarantees no redundant applications.
5. **Verified Evidence of Submission:** Every application marked `applied` includes confirmation text, requisition ID, timestamp, and screenshot evidence.
6. **Automated tests**: `python -m unittest backend.test_api backend.test_prefilter backend.test_scope backend.test_fresher_terms backend.test_batch backend.test_linkedin` (browser tests need `playwright install chromium`).
