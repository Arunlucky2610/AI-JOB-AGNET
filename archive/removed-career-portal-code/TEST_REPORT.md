# Orbit application flow verification — 18 September 2026

All functional checks below were performed through the application browser UI. Shell operations were limited to implementation, server lifecycle and debug inspection.

## Implemented

- Current-posting verification against Greenhouse, Lever and Ashby public APIs; expired listings are rejected. Public API failures fall back to employer-page verification, rather than pretending a vacancy is closed.
- Fresher AI searches prioritize ATS scopes and use alternative role/entry-level terms; salary remains informational.
- Employer pages returning HTTP errors are rejected before model assessment. Known job-news sites Yohire and Hiring Camp are excluded from discovery/application destinations.
- Confirmed profile fields take precedence over resume wording. Duplicate model-generated profile answers and non-text screening values are removed.
- Sponsorship contradictions are blocked during generation, draft saving, approval and application startup. This check is specific; it is not a guarantee that every possible factual error is detected.
- Backend restarts pause in-progress work at saved checkpoints. Interrupted submissions require manual verification instead of automatic retry.
- Expired application browser connections can create a fresh session and reopen the same application. A new session may require signing in again.
- Visible approval queue and document review action; application resume is distinguished from discovery resume.
- Company portal preflight runs from Orbit using Browserbase without filling personal information. Login is shown in the same Live View session. Portal access errors are reported accurately.
- Proxy-enabled session requests fall back to normal sessions when Browserbase returns HTTP 402 for proxy access.
- Whole-form planning remains one model request per visible form inspection, with a response budget that scales with form size.

## Observed browser test results

| Check | Result |
| --- | --- |
| Approval queue in Live agent | Passed: two prepared applications and direct review action displayed |
| Backend unavailable | Passed: visible connection-lost warning reported potentially stale progress |
| Backend restored | Passed: automatic polling cleared the outage warning |
| Cognizant portal preflight from Orbit | Passed: actual employer application portal opened in Browserbase |
| Initial cloud portal access failure | Found: rendered 401 Forbidden page; failure detection added |
| Browserbase proxy availability | HTTP 402 observed; normal-session fallback exercised successfully |
| Cognizant login handoff | Passed: sign-in UI visible in Live View with persistent login notification; no form data entered |
| Contradictory cover letter save | Passed: “I do not require visa sponsorship” rejected with explicit validation error |
| Saved cover letter after rejected edit | Passed: reopening showed original corrected sponsorship statement unchanged |
| Resume preview | Structured headings and project bullet points displayed; saved DOCX download is available |

## Not yet verified

- Expired-session recovery while an actual application form is partially filled.
- Form filling, document upload and employer-confirmed final submission after login.
- Two confirmed real submissions. **Zero real submissions have been verified.**

Cognizant was stopped through Orbit at the user's request. Testing now targets Greenhouse employer portals only. Opening a portal or preparing documents does not count as applying.

## Primary implementation references

- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
- [Ashby Public Job Posting API](https://developers.ashbyhq.com/docs/public-job-posting-api)
- [Browserbase proxies](https://docs.browserbase.com/platform/identity/proxies)

## Greenhouse-only browser run

- Saved Greenhouse-only source focus through Preferences and started the agent through Live agent.
- JobSpy and other company portals were bypassed for this run.
- Two web searches found 12 URLs; current public boards from 10 observed employers supplied 3 India AI/ML vacancies (deduplication resulted in 14 candidate pages).
- All 14 candidate pages were processed through Orbit. Current postings were verified with public ATS GET requests; stale API-confirmed vacancies were skipped before browser navigation/model assessment.
- No eligible application package resulted: graduate AI roles were outside India, current India AI roles required 7-10 years, and quantitative graduate roles had different role/graduation/CGPA restrictions.
- No login gate interrupted this run. No personal documents were uploaded, and zero applications were submitted.
- Fixed daily quota counting: unsubmitted or stopped drafts no longer consume the application-start quota.
- Added source filtering for automatic dispatch and pending approvals so unrelated old drafts cannot hold a Greenhouse run open or be dispatched by it.
- Corrected Live agent UI to show the agent state, scoped approval queue, source focus, and explicitly label matches across all runs.
- Second UI-started run: four simpler role/country queries found 36 URLs; observed employer public boards supplied 13 current India AI/ML vacancies. The completed run inspected 48 candidate entries, including one explicit recheck after a matching correction.
- Found and fixed a false rejection: in broader matching mode, an unstated minimum experience is now a review note rather than a mandatory blocker. The numeric minimum remains null; the product does not assert the vacancy is confirmed fresher-eligible. Explicit experience restrictions remain blockers.
- Rechecked Capco ERDS-MJ - Gen AI Engineer, Greenhouse job 7813741: live API verified; 75% estimated resume/JD fit; minimum experience and required sponsorship both unconfirmed and prominently disclosed.
- Generated a real local Capco application draft. Zero employer submissions have been verified.
- Found and fixed document-generation evidence loss: the model omitted projects/certifications from confirmed resume_text when structured collections were empty. The full uploaded resume is now explicitly included as evidence; relevant projects must be retained.
- Added UI document regeneration with previous approval invalidation and profile/application state checks before saving results.
- Inspected original resume through My profile and compared project claims through Review application. Regenerated final resume includes LangGraph Mini Agent and YouTube Transcript RAG, supported bullet accomplishments and preserved education records; unrelated projects omitted for relevance.
- Cover letter inspected through the UI: relevant project facts retained, no contradictory sponsorship claim.
- Resume preview visually inspected in the browser: prominent name/contact header, section headings and readable paper layout. Standalone DOCX rendering remains unverified.
- Reproduced Next.js proxy socket timeout during long document generation: UI falsely reported server unavailable while FastAPI persisted the regenerated package. Configured experimental.proxyTimeout=120000, above the bounded 90-second model call; repeated UI regeneration successfully returned the new package without that error.
- Added canonical Greenhouse employer/job URLs so board aliases, embed URLs and tracking parameters identify one vacancy. Employer-submit deduplication has not yet been exercised with an actual submission.

## Career Ops integration — 2026-09-18

Follow-up 2026-09-19: continued the specifically approved HARMAN application via Orbit UI. Fixed a slash escaping error in the migration title selector and exposed safe, actionable HTTP error details instead of the generic connection-interrupted message. The prior Browserbase session had expired; two UI-triggered recovery attempts could not create a replacement. The final activity log reports Browserbase HTTP 402 for a normal, non-proxy session. Application is needs_input, no form filling or submission verified. Billing/credit access must be restored before this test can continue. The replacement-portal migration selector fix remains unverified end to end.

- Imported the five public discovery providers, liveness checks, adapted A–H evaluation/evidence rules and original resume/cover-letter HTML templates from pinned Career Ops 1.33.0. MIT notices retained. DeepSeek remains the only model.
- Functional checks ran through the real Orbit UI. Started discovery with all company portals and broad India fresher AI preferences; no salary filtering. JobSpy source errors and the unavailable Temporal board were visibly reported rather than represented as zero vacancies.
- Live feed discovery produced 4,413 unique postings and prioritized 337 role candidates. The bounded inspection queue contains 60 candidates; these counts do not mean 337 eligible jobs.
- Actual agent inspection covered Workday, Ashby and Greenhouse. It generated a HARMAN Associate Engineer AI/ML draft (95% estimated fit) and rejected HARMAN Advanced Engineer (5–7 years), Gradera ML Engineer (3+ years) and Capco AI Engineer (5–10 years). Four completed evaluations observed before pausing. Lever/SmartRecruiters are integrated but were not independently exercised end to end in this run.
- Fixed truncated/missing evaluation output, overly strict city/work-mode handling in manual assessment, whitespace country mismatches, and unsupported/paraphrased profile citations. Report rows now resolve confirmed evidence IDs and explicit quoted critical requirements constrain eligibility.
- Regenerated the existing Capco draft through the UI, preserving relevant projects, education and certifications. Fixed empty-template-section removal and stale iframe previews after regeneration.
- UI-created resume and cover-letter PDFs were rendered and visually checked: readable one-page A4 layouts, no template placeholders or clipped sections. Checked the latest corrected HARMAN resume export too. The in-app PDF viewer remains blank; actual exported PDFs render correctly with Poppler.
- Alternate HARMAN posting/apply URLs opened the same application ID through Prepare application, with the review queue remaining at three drafts. Legacy duplicate job cards remain in historical results; actual employer-submit deduplication is not verified.
- Found and manually corrected overstated production-readiness wording in the HARMAN draft through Edit document / Save draft. Added a deterministic generation guard for unsupported production-grade/production-ready/enterprise-grade labels. That new guard has not yet been exercised by a fresh generation request.
- Required India visa sponsorship remains unconfirmed for the HARMAN vacancy and is disclosed in the draft. A high fit score does not establish sponsorship eligibility.
- Next.js typecheck passed. Backend restarted successfully after final changes. Agent is paused; approval mode remains per application. No employer document uploads or submissions occurred in this integration test. Zero confirmed submissions.
