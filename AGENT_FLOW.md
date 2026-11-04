# Agent flow

Orbit applies to jobs on **LinkedIn** only. Employer career pages (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, JobSpy, company portals) and Naukri were removed; the old code is in `archive/removed-career-portal-code/`. Indeed was removed as well (its bot detection signed out every new cloud browser); its code is in `archive/removed-indeed-code/`.

## Connect your accounts before the agent applies
On the Live agent page, **Start agent stays disabled until LinkedIn shows as connected.** Clicking Connect LinkedIn opens a small live browser embedded right there for the person to sign in; once the sign-in completes the session closes itself and the platform is marked connected (`/api/connections/<platform>/check`, polled every few seconds while the card is open). This uses the same saved Browserbase profile as a real run, so once signed in the person is not asked again on later visits — if a run later discovers the saved session has actually expired, its own sign-in check (below) still catches it and pauses for a fresh sign-in, which also re-marks the platform connected.

## How a LinkedIn run works

1. **Sign-in check.** The agent opens LinkedIn in a Browserbase cloud browser that carries the user's saved login profile. If LinkedIn shows a sign-in or security check, the run pauses ("Login required") and the person signs in through Live View with email and password (Google/Apple buttons open a hidden popup, which the agent closes and explains). The agent never types passwords or solves CAPTCHAs. After Resume it continues. The login is saved for later runs.
2. **Search.** From the confirmed profile it builds LinkedIn job searches: role keywords, location, Easy Apply only, experience level from the **career stage** (Intern, Fresher, Experienced), past week, newest first. Interns and freshers also search junior Python/Software roles. It reads the results list (first page per search) and dedupes by vacancy.
3. **A funnel, cheapest check first.** Nothing costs a model call until it has to. Known jobs are skipped from the database. The search cards' titles drop senior and off-topic roles **without opening the page**. On the page, a free text check drops postings that ask for more years than the profile has ("2+ years", "minimum 3 years"; company boasting and "preferred" are ignored). **Jev** (`JEV_MODE`: shadow logs only, active skips confident rejects, off) then triages in about 2 seconds with small yes/no and pick-one questions. Only what survives reaches DeepSeek.
4. **Two-step assessment.** A short DeepSeek call (a few seconds) scores fit for every surviving job. Only a job that already looks like a match gets the long evidence report (asked for twice if the first reply lacks it). Document writing runs with hidden reasoning off (`NO_THINKING`), which cut it from 15-45 s to 6-8 s.
5. **Apply in the background.** Tailored documents are written, then Easy Apply runs in its own tab while the agent keeps reviewing the next jobs. Only one application runs at a time. Routine steps (contact details, upload, review and submit) are planned by rules with no model call; DeepSeek plans only steps with questions. Fields are filled from confirmed answers only; a form the agent cannot answer truthfully is skipped and listed for the person.
6. **Limits.** The daily limit from Preferences (max 10) counts real submissions; skipped or stopped attempts do not use it, but a cap of four times the limit (at least limit + 10) attempts per day stops a loop that keeps failing. 3 to 7 seconds between page visits. Each run also stops at `RUN_BUDGET_USD` of model spend (default 1.00), shown live on the Live agent page. Approval modes: one at a time, batch, or automatic (explicitly enabled).

## What the agent needs from you
It never guesses about you. When a form asks something with no approved answer, that job is skipped and the question appears on the Live agent page ("The agent needs N answers from you"). Fix it once on your profile and the skipped jobs are retried on the next run:
- **Years per skill** for "years of experience with X" questions (My profile, Job preferences, Skills).
- **Common application questions** (background check, drug test, on-site, shifts, laptop, bond, degree completed): Yes or No once, in My profile, Eligibility.
- **Approved answers** for anything else, one per line.

## Safety rules that always apply
- Sign-in, verification, CAPTCHA and consent are the person's. The agent pauses and waits.
- An unclear submission becomes `needs_verification` and is never retried automatically.
- Every application needs the exact document package to be unchanged since approval (automatic mode enabled by the person is the only exception).
- Only pages on the job site itself are allowed application destinations.

## Costs and limits to know
- Browserbase minutes are consumed while a session is open, including while waiting for the person to sign in.
- Model spend is tracked per run from OpenRouter's reported cost; the key's own limit is separate and stops every call with HTTP 403 when reached (the agent stops with a clear message).
- Automating LinkedIn breaks its terms of use; accounts that apply in bulk can be restricted.
