# Career Ops integration

Pinned upstream: https://github.com/career-ops-hq/career-ops
Version 1.33.0, commit ff2945c98dea92754b7d270bf03aea0bc53c6ac3.
Source lives in vendor/career-ops; preserve its MIT LICENSE and copyright notice.
Orbit remains the product name. No upstream CLI, subscription, AI provider,
candidate profile, tracker, or web UI is run or imported.

- backend/career_ops_bridge.mjs directly imports the upstream Greenhouse,
  Ashby, Lever, Workday and SmartRecruiters public providers and HTTP guards.
- Public boards discovered by Orbit's internet search expand into feeds.
  backend/career_ops_portals.json supplies a bounded starter set adapted from
  upstream's template. Feed failures are logged separately from empty boards.
- Discovery ranks target-role/geography/junior signals before assessment.
  Remote does not imply worldwide eligibility; unstated experience does not
  establish fresher suitability. Existing approval and login gates remain.
- Upstream liveness-api and liveness-core run before document generation;
  transient failures are uncertain, not proof that a job is closed.
- Upstream Block B evidence/importance rules feed the pinned DeepSeek model
  in the same assessment call. Orbit validates quoted evidence and displays
  the adapted A-H report. Salary never filters candidates. Global 1-5 and
  percentage fit scores are estimates, not an employer ATS score.
- Original CV and cover-letter HTML templates render saved packages in the
  application review. PDF export uses local Edge; DOCX remains available.
  Resume facts are drawn only from the confirmed profile/uploaded resume.

Runtime: Node 18+, Python requirements, local Microsoft Edge for PDF export.
No npm install in the vendor checkout is needed for these provider modules.
New agent runs activate the provider integration; resuming older discovery
checkpoints retains their prior candidate queue.

Confirmed profile evidence is supplied with stable per-request IDs. Returned
citations are checked against that catalog and the actual JD; unsupported
strong/partial claims become unknown. Critical missing requirements block
eligibility. Scores cannot override those requirements.
Workday requisitions, Greenhouse aliases and Lever/Ashby application suffixes
reuse existing vacancies and drafts. Legacy history is retained, not migrated.
Discovery is bounded (35 boards, paginated providers and a 60-page evaluation
queue), not a complete search of every employer. Unknown sponsorship remains
disclosed for review under the saved broader fresher matching mode.
