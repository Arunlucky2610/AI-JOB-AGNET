# Jev versus DeepSeek browser decisions

Tested 2026-09-19 using the configured OpenRouter credential. No personal data,
employer interactions or application submissions were used for this comparison.

| Model | Expected answers | Median request time |
|---|---:|---:|
| typesafe/jev-1.13 | 45/48 | 0.756 seconds |
| deepseek/deepseek-v4-flash-0731 | 48/48 | 13.056 seconds |

Sixteen synthetic cases were repeated three times, with model order alternated.
Both models received the same state, question instructions and choice criteria.
Cases cover step navigation, hidden resume upload, final submission, login/OTP,
terms, parsing readiness, migrated portals, missing fields, page injection,
ambiguous controls, new versus stale confirmation, and saved-field mappings.

Jev uses POST /api/alpha/decisions; chat/completions rejects this decisions model.
Its returned version was typesafe/jev-1.13-20260917. DeepSeek used the existing
low-reasoning, temperature 0.2, structured-JSON configuration. All six completed
requests produced parseable answers. Each request answered all sixteen cases.

Jev's only discrepancy repeated in every trial: it chose human review rather
than the explicitly saved sponsorship field when citizenship was also present.
This is a conservative false pause, not an unsafe submission decision. Both
models correctly classified the isolated upload and Next-versus-Submit cases.

Decision: retain DeepSeek as the production planner. Jev was approximately
17.3 times faster by median batch latency, but did not improve correctness on
this small test. Speed alone is insufficient to replace the complete planner.

Limits: these are author-labelled, compact synthetic states derived from
observed failure modes, not recorded full DOM replays. Repeating sixteen cases
does not create 48 independent cases. This test does not measure executable
multi-action plans, actual uploads, browser latency, or end-to-end submission.
Results cannot establish general model superiority. Jev remains a candidate
for a narrowly scoped classifier after larger DOM replay tests.

Reproduce: `.venv\Scripts\python.exe tools/compare_browser_decisions.py`
Raw results and per-case answers: browser-model-comparison.json.
No runtime model settings were changed.
