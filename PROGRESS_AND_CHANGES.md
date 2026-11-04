# Orbit: Task 1 and Task 2

Date: 2026-10-14

---

# TASK 1: Understand the current progress of the agent

## 1.1 What the agent does today (working)
1. Opens LinkedIn in a cloud browser with your saved login.
2. Searches Easy Apply jobs using your roles, location and career level.
3. Drops bad jobs cheaply: senior titles, "3+ years" jobs, off-topic jobs.
4. Scores fit with the AI model (DeepSeek).
5. Writes a tailored resume and cover letter.
6. Fills the Easy Apply form and submits.
7. Marks "Applied" only when LinkedIn confirms it.
8. Stops for you on login, CAPTCHA, or a question it cannot answer.

## 1.2 What is NOT working or missing (compared with `GOALS 1.md`)

| Goal says | Reality in code |
|---|---|
| Apply on company sites (Greenhouse, Lever, Ashby, Workday) | Removed on purpose. Code is in `archive/`. |
| Check every job is still open | Only a small "no longer accepting" check on LinkedIn. |
| Remove duplicates across sites | Only by URL. No cross-site matching. |
| Track results after applying (interview, rejected) | No code existed. |
| Apply to fewer, better jobs | Fit bar was only 40%. |
| Respect the roles you want | Fresher mode replaced your roles with a fixed AI list. |

## 1.3 Why it felt like "automation of a word"
- Skipping jobs was done by matching words in titles.
- Skipping by experience was done by matching text like "3+ years".
- Your own target role could be overwritten.
- The agent never learned whether an application led anywhere.

## 1.4 Test status
- Non-browser tests pass (`test_api` 29/29, prefilter, scope, fresher terms, batch).
- Browser tests fail on this computer only because Chromium is not installed. They failed the same way before our changes.

---

# TASK 2: Make the agent meet the goals, not just automate a word

Direction you chose: **LinkedIn-only, goal-driven.**

## 2.1 Changes made

| # | Goal | Change | Where |
|---|---|---|---|
| 1 | Search for what YOU want | Your roles are kept and searched first. Similar roles are added only in your direction. "Marketing Executive" is never searched as "AI Engineer". | `platform_agent.py`, `main.py` |
| 2 | Fewer, better jobs | Minimum fit for freshers raised from 40% to 60%. | `platform_agent.py` (`MIN_FIT`) |
| 3 | Title filter follows your goal | A job title is judged against your own roles, not a fixed AI word list. | `platform_agent.py` |
| 4 | Know if applications work | After you apply you can record: waiting, shortlisted, assessment, interview, offer, rejected, no response. Also thumbs up/down and a note. | `db.py`, `main.py` |
| 5 | Measure success | Shortlist rate = applications that moved forward out of all submitted. | `GET /api/outcomes/summary` |
| 6 | Goals file matches reality | `GOALS 1.md` now says LinkedIn-only and lists what is built and not built. | `GOALS 1.md` |

## 2.2 New endpoints
- `PUT /api/applications/{id}/outcome` saves the result. Only submitted applications are allowed.
- `GET /api/outcomes/summary` returns totals, stage counts and shortlist rate.

## 2.3 Tests added
- Outcome tracking works and keeps earlier values on partial updates.
- Outcome rejected for non-submitted applications and invalid stages.
- Non-tech roles are not widened to AI.
- Title filter follows the person's own role.
- Fit floor is exactly 60.

## 2.4 Still not done for Task 2
1. **No screen buttons** for outcome tracking. Backend only.
2. **Keyword rules remain** for senior titles and years-of-experience.
3. **No best-first ranking.** It applies as good jobs appear.
4. **Not committed to git.**

## 2.5 Next step
Add the outcome buttons and shortlist-rate panel to the app screen.

---

Files changed: `backend/db.py`, `backend/main.py`, `backend/platform_agent.py`, `backend/test_api.py`, `backend/test_linkedin.py`, `GOALS 1.md`, `PROGRESS_AND_CHANGES.md`.
