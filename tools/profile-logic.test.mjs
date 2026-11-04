// Run: node --test tools/profile-logic.test.mjs   (Node 22+ runs the .ts file directly)
import test from 'node:test';
import assert from 'node:assert/strict';
import * as L from '../app/profile-logic.ts';

const today = new Date('2026-09-21T10:00:00');
const good = () => ({
  name: 'Sai Varshith', email: 'sai@example.com', phone: '+91 6303391412', address: '12 Main Road, Hyderabad, Telangana 500001', resume_text: 'x'.repeat(80), portfolio: 'https://github.com/sai',
  career_level: 'Fresher', education: [{ degree: 'Bachelor’s degree', school: 'Mallareddy University', year: '2026', major: 'Computer Science' }], work_history: [], no_experience: true, experience: 0,
  roles: 'AI Engineer, Python Developer', country: 'India', locations: 'Hyderabad', skills: 'Python, FastAPI', work_modes: ['Hybrid'], employment_type: 'Full-time', availability: 'Immediately', relocation: 'Yes', salary: '50000',
  eligibility: 'Citizen', sponsorship: 'No', authorization: 'Citizen of India, authorized to work without sponsorship', age_confirmed: true,
});

test('the country list is clean and complete enough to pick from', () => {
  assert.equal(new Set(L.COUNTRIES).size, L.COUNTRIES.length, 'no duplicates');
  assert.ok(L.COUNTRIES.length >= 190);
  for (const c of ['India', 'United States', 'United Kingdom', 'Canada', 'Germany', 'Singapore', 'United Arab Emirates']) assert.ok(L.COUNTRIES.includes(c), c);
  for (const [name, code] of L.COUNTRY_TABLE) assert.match(code, /^\+\d{1,3}$/, name);
  for (const top of L.TOP_COUNTRIES) assert.ok(L.COUNTRIES.includes(top), top);
});

test('countries typed or saved earlier are normalised to the official name', () => {
  for (const [input, expected] of [['india', 'India'], [' INDIA ', 'India'], ['USA', 'United States'], ['u.s.', 'United States'], ['UK', 'United Kingdom'], ['uae', 'United Arab Emirates'], ['Czechia', 'Czech Republic'], ['Türkiye', 'Turkey']])
    assert.equal(L.normalizeCountry(input), expected, input);
  for (const bad of ['', 'Hyderabad', 'Narnia', 'In', 'Ind']) assert.equal(L.normalizeCountry(bad), null, bad);
});

test('currency follows the country and every default is offered in the list', () => {
  assert.equal(L.defaultCurrency('India'), 'INR'); assert.equal(L.defaultCurrency('usa'), 'USD'); assert.equal(L.defaultCurrency('Germany'), 'EUR'); assert.equal(L.defaultCurrency(''), 'USD');
  const offered = new Set(L.CURRENCIES.map(([code]) => code));
  for (const country of L.COUNTRIES) assert.ok(offered.has(L.defaultCurrency(country)), country);
});

const BLOB = ', AI / GenAI / Agentic: LangChain, LlamaIndex, LangGraph, ChromaDB, HuggingFace Embeddings & Endpoints, RAG, Pipelines, n8n AI Automation, Scikit-learn, LLMs & APIs: Llama-3-70B (HuggingFace), Gemini 1.5 Flash, OpenAI API, REST API design, FastAPI, JSON handling, Frontend: React.js, Next.js, JavaScript (ES6), TypeScript, HTML5, CSS3, Redux, Chrome Extension API, Backend & Databases: Python, FastAPI, Flask, Node.js  |  ChromaDB, SQL, MongoDB, SQLite, Tools: Git, Linux, Jupyter Notebooks, Uvicorn';
test('a pasted resume skills blob becomes a clean list', () => {
  const skills = L.parseSkillList(BLOB);
  for (const wanted of ['LangChain', 'Llama-3-70B (HuggingFace)', 'JavaScript (ES6)', 'Python', 'Node.js', 'Jupyter Notebooks', 'HuggingFace Embeddings & Endpoints', 'React.js'])
    assert.ok(skills.includes(wanted), 'missing ' + wanted);
  for (const label of ['Frontend', 'Tools', 'Backend & Databases', 'AI / GenAI / Agentic', 'LLMs & APIs']) assert.ok(!skills.some(s => s.startsWith(label)), 'label kept: ' + label);
  assert.equal(skills.filter(s => s.toLowerCase() === 'fastapi').length, 1, 'no repeats');
  assert.equal(skills.filter(s => s.toLowerCase() === 'chromadb').length, 1);
  assert.ok(skills.every(s => s && s === s.trim() && !/^[,|:;-]/.test(s)), 'no empty or dirty entries');
  assert.equal(skills.length, 33, 'the blob holds 33 distinct skills once labels and repeats are removed');
});
test('ordinary skill lists are left alone and messy ones are detected', () => {
  assert.deepEqual(L.parseSkillList('Python, SQL,  React '), ['Python', 'SQL', 'React']);
  assert.deepEqual(L.parseSkillList('Skills: Python, SQL'), ['Python', 'SQL']);
  assert.deepEqual(L.parseSkillList('- Python\n- SQL\n• Git'), ['Python', 'SQL', 'Git']);
  assert.deepEqual(L.parseSkillList('C++, C#, .NET'), ['C++', 'C#', '.NET']);
  assert.deepEqual(L.parseSkillList(''), []);
  assert.equal(L.skillsLookMessy(BLOB), true); assert.equal(L.skillsLookMessy('Python, SQL, React'), false); assert.equal(L.skillsLookMessy(', Python'), true);
});
test('lists of roles and cities split on commas, semicolons and lines', () => {
  assert.deepEqual(L.splitList('AI Engineer, ML Engineer; Data Analyst\nai engineer'), ['AI Engineer', 'ML Engineer', 'Data Analyst']);
  assert.equal(L.joinList(['a', 'b']), 'a, b');
});

test('phone numbers split into a country code and a number', () => {
  assert.deepEqual(L.splitPhone('+91 6303391412', '+1'), { code: '+91', number: '6303391412' });
  assert.deepEqual(L.splitPhone('+916303391412', '+1'), { code: '+91', number: '6303391412' });
  assert.deepEqual(L.splitPhone('+1 (212) 555-1234', '+91'), { code: '+1', number: '(212) 555-1234' });
  assert.deepEqual(L.splitPhone('6303391412', '+91'), { code: '+91', number: '6303391412' });
  assert.deepEqual(L.splitPhone('', '+44'), { code: '+44', number: '' });
  assert.equal(L.joinPhone('+91', ' 6303391412 '), '+91 6303391412'); assert.equal(L.joinPhone('+91', ''), '');
});
test('phone problems are explained', () => {
  assert.equal(L.phoneProblem('+91 6303391412'), ''); assert.equal(L.phoneProblem('9876543210'), '');
  assert.match(L.phoneProblem(''), /Enter your mobile number/); assert.match(L.phoneProblem('+91 123'), /valid mobile number/); assert.match(L.phoneProblem('+91 12345678901234567'), /valid mobile number/);
});

test('a start date in the past is caught, relative answers are fine', () => {
  assert.match(L.startDateProblem('2004-09-09', today), /has passed/);
  assert.equal(L.startDateProblem('2026-09-21', today), '', 'today is fine');
  assert.equal(L.startDateProblem('2026-12-01', today), '');
  assert.equal(L.startDateProblem('Immediately', today), ''); assert.equal(L.startDateProblem('Within 1 month', today), '');
  assert.match(L.startDateProblem('', today), /Choose when/); assert.match(L.startDateProblem('garbage', today), /Choose when/);
});

test('the work authorization statement follows the eligibility answer', () => {
  assert.match(L.authorizationText('Citizen', 'india'), /Citizen of India/); assert.match(L.authorizationText('Need work authorization', 'Canada'), /Requires work authorization to work in Canada/);
  assert.equal(L.authorizationText('', 'India'), ''); assert.equal(L.authorizationText('Other', 'India'), '');
});

test('a complete profile has no errors on any step', () => {
  for (let step = 0; step <= 3; step++) assert.deepEqual(L.validateStep(good(), step, today), {}, 'step ' + step);
  assert.deepEqual(L.validateAll(good(), today), []);
});
test('every problem is reported on its own field in plain words', () => {
  const step0 = L.validateStep({ ...good(), name: '', email: 'nope', phone: '', address: 'x', resume_text: '', portfolio: 'linkedin.com/in/x' }, 0, today);
  assert.deepEqual(Object.keys(step0).sort(), ['address', 'email', 'name', 'phone', 'portfolio', 'resume_text']);
  const step2 = L.validateStep({ ...good(), roles: '', country: 'Hyderabad', locations: '', skills: ', ', work_modes: [], employment_type: '', availability: '2004-09-09', relocation: '', salary: 'lots' }, 2, today);
  assert.deepEqual(Object.keys(step2).sort(), ['availability', 'country', 'employment_type', 'locations', 'relocation', 'roles', 'salary', 'skills', 'work_modes']);
  assert.match(step2.country, /from the list/); assert.match(step2.availability, /has passed/);
  for (const message of [...Object.values(step0), ...Object.values(step2)]) assert.doesNotMatch(message, /[a-z]_[a-z]/, 'no raw keys in: ' + message);
});
test('education and work rows are checked one by one', () => {
  const p = { ...good(), education: [{ degree: '', school: '', year: '', major: '' }], career_level: 'Experienced', no_experience: false, experience: 0, work_history: [{ title: '', company: '', start: '2024-05', end: '2023-01', current: false, responsibilities: '' }] };
  const e = L.validateStep(p, 1, today);
  for (const key of ['education.0.degree', 'education.0.school', 'education.0.year', 'education.0.major', 'work.0.title', 'work.0.company', 'work.0.end', 'work.0.responsibilities', 'experience']) assert.ok(e[key], key);
  assert.match(e['work.0.end'], /after the start/);
  assert.equal(L.validateStep({ ...p, work_history: [] }, 1, today).work_history, 'Add your work experience.');
});
test('freshers and interns are not forced to add work experience', () => {
  for (const level of ['Fresher', 'Intern']) assert.equal(L.validateStep({ ...good(), career_level: level, work_history: [], no_experience: true }, 1, today).work_history, undefined, level);
  assert.match(L.validateStep({ ...good(), career_level: '' }, 1, today).career_level, /Choose/);
});
test('eligibility step needs every answer', () => {
  const e = L.validateStep({ ...good(), eligibility: '', sponsorship: '', authorization: ' ', age_confirmed: false }, 3, today);
  assert.deepEqual(Object.keys(e).sort(), ['age_confirmed', 'authorization', 'eligibility', 'sponsorship']);
});
test('every validated field has a human label', () => {
  const all = ['name', 'email', 'phone', 'portfolio', 'address', 'resume_text', 'career_level', 'education', 'work_history', 'experience', 'roles', 'country', 'locations', 'skills', 'work_modes', 'employment_type', 'availability', 'relocation', 'salary', 'eligibility', 'sponsorship', 'authorization', 'age_confirmed'];
  for (const key of all) assert.ok(L.FIELD_LABELS[key], key);
});
test('contradictory eligibility answers get a warning, not an error', () => {
  assert.match(L.sponsorshipWarning({ eligibility: 'Citizen', sponsorship: 'Yes', country: 'India' }), /citizen of India but said you need sponsorship/);
  assert.match(L.sponsorshipWarning({ eligibility: 'Need work authorization', sponsorship: 'No', country: 'India' }), /Check that these match/);
  assert.equal(L.sponsorshipWarning({ eligibility: 'Citizen', sponsorship: 'No', country: 'India' }), '');
});
test('graduation years run from a few years ahead back to 1970', () => {
  const years = L.graduationYears(new Date('2026-09-21')); assert.equal(years[0], '2032'); assert.equal(years.at(-1), '1970'); assert.ok(years.includes('2026'));
});
test('city suggestions follow the country', () => {
  assert.ok(L.citySuggestions('india').includes('Hyderabad')); assert.deepEqual(L.citySuggestions('Narnia'), ['Remote']);
});

test('common application questions are stored as plain approved-answer lines', () => {
  let text = 'Are you comfortable with night shifts? Yes';
  assert.deepEqual(L.commonAnswers(text), {});
  text = L.setCommonAnswer(text, 'drugtest', 'Yes');
  text = L.setCommonAnswer(text, 'background', 'No');
  assert.equal(text, ['Are you comfortable with night shifts? Yes', 'Are you willing to undergo a drug test? Yes', 'Are you willing to undergo a background check? No'].join('\n'));
  assert.deepEqual(L.commonAnswers(text), { drugtest: 'Yes', background: 'No' });
  text = L.setCommonAnswer(text, 'drugtest', 'No');
  assert.equal(L.commonAnswers(text).drugtest, 'No'); assert.equal(text.split('drug test').length, 2, 'changed in place, not duplicated');
  text = L.setCommonAnswer(text, 'background', '');
  assert.deepEqual(L.commonAnswers(text), { drugtest: 'No' }); assert.match(text, /night shifts\? Yes/);
  assert.equal(L.setCommonAnswer('', 'laptop', ''), ''); assert.deepEqual(L.commonAnswers(''), {});
  assert.deepEqual(L.commonAnswers('Are you willing to undergo a drug test? Maybe'), {});
});
