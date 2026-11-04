'use client';
import {useEffect, useMemo, useRef, useState} from 'react';
import {Orbit, Upload, ArrowRight, ArrowLeft, Check, Plus, Trash2, FileText, ShieldCheck, LoaderCircle, AlertCircle, Pencil} from 'lucide-react';
import * as L from './profile-logic';
import {Field, ChoiceCards, TagInput, SkillsEditor} from './profile-ui';

export type Education = {degree: string; school: string; year: string; major: string};
export type Work = {title: string; company: string; start: string; end: string; current: boolean; responsibilities: string};
export type Project = {name: string; description: string; url: string; technologies: string};
export type Certification = {name: string; issuer: string; year: string};
export type Candidate = {
  name: string; email: string; phone: string; address: string; current_location?: string;
  roles: string; country: string; locations: string; work_modes: string[]; experience: number;
  skills: string; salary: string; currency: string; pay_period: string; authorization: string;
  sponsorship: string; notice: string; portfolio: string; portfolio_url?: string;
  github?: string; github_url?: string; linkedin?: string; linkedin_url?: string;
  summary?: string; preferred_industries?: string; preferred_companies?: string;
  resume_text: string; screening: string; excluded_companies: string;
  strict_location: boolean; strict_country: boolean; strict_mode: boolean; confirmed: boolean;
  education: Education[]; work_history: Work[]; projects?: Project[]; certifications?: Certification[];
  cover_letter_text: string; availability: string; relocation: string; employment_type: string;
  eligibility: string; age_confirmed: boolean; eeo_gender: string; eeo_ethnicity: string;
  eeo_disability: string; eeo_veteran: string; no_experience: boolean; resume_filename: string;
  career_level: string; skill_years: Record<string, number>;
};
type Props = {initial: Candidate; onSave: (p: Candidate) => Promise<void>; onComplete: () => void; editing?: boolean};

/** Real, confirmed places matching `q` (server-side LocationIQ lookup; empty without a configured key).
 * `label` (with state/country) is shown so the right one is picked; `value` (just the city) is what's
 * stored, since the profile keeps this field as one comma-joined string. */
async function lookupCities(q: string): Promise<{label: string; value: string}[]> {
  try {
    const r = await fetch(`/api/geocode/cities?q=${encodeURIComponent(q)}`);
    if (!r.ok) return [];
    const data = await r.json();
    return Array.isArray(data.results) ? data.results.map((row: {label: string; city: string}) => ({label: row.label, value: row.city})) : [];
  } catch { return []; }
}

const steps = ['You & your resume', 'Education & experience', 'Job preferences', 'Eligibility & answers', 'Review & confirm'];
const emptyEducation: Education = {degree: '', school: '', year: '', major: ''};
const emptyWork: Work = {title: '', company: '', start: '', end: '', current: false, responsibilities: ''};
const todayIso = () => new Date().toISOString().slice(0, 10);
const monthOf = (date: string) => (date || '').slice(0, 7);

type SelectProps = {value: string; onChange: (value: string) => void; options: (string | [string, string])[]; placeholder?: string; props: Record<string, unknown>; groups?: {label: string; options: string[]}[]};
function PSelect({value, onChange, options, placeholder = 'Choose an option', props, groups}: SelectProps) {
  return (
    <select {...props} value={value} onChange={e => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {groups ? groups.map(g => <optgroup key={g.label} label={g.label}>{g.options.map(o => <option key={o}>{o}</option>)}</optgroup>)
        : options.map(o => typeof o === 'string' ? <option key={o}>{o}</option> : <option key={o[0]} value={o[0]}>{o[1]}</option>)}
    </select>
  );
}

export default function Onboarding({initial, onSave, onComplete, editing = false}: Props) {
  const [p, setP] = useState<Candidate>(initial);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showErrors, setShowErrors] = useState(false);
  const [extracted, setExtracted] = useState<string[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [tidied, setTidied] = useState<string[]>([]);
  const [askAuth, setAskAuth] = useState(false);
  const formRef = useRef<HTMLElement>(null);
  const lastAuto = useRef(L.authorizationText(initial.eligibility, initial.country));

  const set = (patch: Partial<Candidate>) => setP(old => ({...old, ...patch, confirmed: false}));
  const errors = useMemo(() => L.validateStep(p, step), [p, step]);
  // A start date that has already passed is flagged as soon as it is shown; other problems wait until the person tries to continue.
  const err = (key: string) => (showErrors || (key === 'availability' && /^\d{4}-/.test(p.availability)) ? errors[key] : undefined);
  const skillList = useMemo(() => L.parseSkillList(p.skills), [p.skills]);
  const country = L.normalizeCountry(p.country) || '';

  // Tidy what earlier versions or the resume reader left behind, once, and say what changed.
  useEffect(() => {
    const said: string[] = [];
    const next = {...initial};
    if (L.skillsLookMessy(initial.skills)) { next.skills = L.joinList(L.parseSkillList(initial.skills)); said.push('Your skills were tidied into a clean list. Please check them.'); }
    const canonical = L.normalizeCountry(initial.country);
    if (canonical && canonical !== initial.country) next.country = canonical;
    if (initial.availability && !L.START_OPTIONS.includes(initial.availability) && L.startDateProblem(initial.availability, new Date())) said.push('Your start date is in the past. Choose when you can start on the Job preferences step.');
    if (initial.currency === 'USD' && canonical === 'India' && !initial.salary) next.currency = 'INR';
    setP(next);
    setTidied(said);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // The work authorization statement follows the eligibility answer until the person edits it.
  useEffect(() => {
    const suggestion = L.authorizationText(p.eligibility, p.country);
    if (!suggestion) return;
    setP(old => {
      if (old.authorization && old.authorization !== lastAuto.current) return old;
      lastAuto.current = suggestion;
      return {...old, authorization: suggestion};
    });
  }, [p.eligibility, p.country]);

  // People looking for jobs in India are Indian citizens who need no sponsorship: answer those questions for them.
  const citizenAtHome = country === 'India' && !askAuth && ['', 'Citizen'].includes(p.eligibility);
  const atHome = citizenAtHome;
  useEffect(() => {
    if (!citizenAtHome) return;
    const statement = L.authorizationText('Citizen', 'India');
    const weak = p.authorization.trim().length < 12; // an old "yes" or an empty box is not a statement
    if (p.eligibility === 'Citizen' && p.sponsorship === 'No' && !weak) return;
    setP(old => ({...old, eligibility: 'Citizen', sponsorship: 'No', authorization: old.authorization.trim().length < 12 ? statement : old.authorization}));
  }, [citizenAtHome, p.eligibility, p.sponsorship, p.authorization]);

  const upload = async (file: File, cover = false) => {
    setBusy(true); setError('');
    try {
      const body = new FormData(); body.append('file', file);
      const response = await fetch('/api/profile/resume', {method: 'POST', body});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail);
      if (cover) { set({cover_letter_text: data.text}); return; }
      setP(old => {
        const next: Candidate = {...old, resume_text: data.text, resume_filename: file.name, confirmed: false};
        for (const [key, value] of Object.entries(data.fields || {})) {
          const current = old[key as keyof Candidate];
          if (!current || (Array.isArray(current) && !current.length)) (next as unknown as Record<string, unknown>)[key] = value;
        }
        next.skills = L.joinList(L.parseSkillList(next.skills));
        return next;
      });
      setExtracted(Object.keys(data.fields || {}));
      setNotes(data.notes || []);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not read this document.'); }
    finally { setBusy(false); }
  };

  const focusFirstError = () => requestAnimationFrame(() => {
    const first = formRef.current?.querySelector<HTMLElement>('[data-error="true"]');
    first?.scrollIntoView({behavior: 'smooth', block: 'center'});
    first?.querySelector<HTMLElement>('input,select,textarea,button')?.focus({preventScroll: true});
  });
  const issues = useMemo(() => L.validateAll(p), [p]);
  const go = (to: number) => { setStep(to); setError(''); setShowErrors(false); formRef.current?.scrollIntoView({block: 'start'}); };

  /** What is saved: clean lists, an official country name, and years only for skills that are still listed. */
  const finalize = (value: Candidate): Candidate => {
    const skills = L.parseSkillList(value.skills);
    const years: Record<string, number> = {};
    for (const skill of skills) if (value.skill_years?.[skill] !== undefined) years[skill] = value.skill_years[skill];
    const fresher = value.career_level !== 'Experienced';
    return {...value, roles: L.joinList(L.splitList(value.roles)), locations: L.joinList(L.splitList(value.locations)), skills: L.joinList(skills), skill_years: years,
      country: L.normalizeCountry(value.country) || value.country, no_experience: fresher ? !value.work_history.length : false, experience: fresher ? 0 : value.experience};
  };
  const next = async () => {
    if (step === 4) {
      if (issues.length) { setError(`${issues.reduce((n, x) => n + Object.keys(x.errors).length, 0)} details still need your attention. Use the links above to fix them.`); return; }
      if (!p.confirmed) { setError('Tick the box to confirm your details are accurate.'); return; }
    } else if (Object.keys(errors).length) {
      setShowErrors(true);
      const count = Object.keys(errors).length;
      setError(`Please fix ${count} ${count === 1 ? 'field' : 'fields'} marked in red to continue.`);
      focusFirstError();
      return;
    }
    setBusy(true); setError('');
    try {
      const saved = finalize({...p, confirmed: step === 4 ? p.confirmed : false});
      await onSave(saved); setP(saved);
      if (step === 4) onComplete(); else go(step + 1);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save your profile.'); }
    finally { setBusy(false); }
  };

  // ---- pieces --------------------------------------------------------------------------------------------
  const phoneCode = L.DIAL_CODES[country] || '+91';
  const phone = L.splitPhone(p.phone, phoneCode);
  const startIsDate = !!p.availability && !L.START_OPTIONS.includes(p.availability);
  const setEducation = (i: number, patch: Partial<Education>) => set({education: p.education.map((row, n) => n === i ? {...row, ...patch} : row)});
  const setWork = (i: number, patch: Partial<Work>) => set({work_history: p.work_history.map((row, n) => n === i ? {...row, ...patch} : row)});
  const common = L.commonAnswers(p.screening);
  const warning = L.sponsorshipWarning({eligibility: p.eligibility, sponsorship: p.sponsorship, country: country || p.country});
  const suggested = (key: string) => (extracted.includes(key) ? 'Suggested from your resume. Please review.' : undefined);

  return (
    <div className={`onboarding ${editing ? 'editing' : ''}`}>
      <header className="onboarding-header"><a className="brand brand-logo"><img src="/rapidskill-logo.png" alt="Rapidskill"/><small>AI Job Apply Agent</small></a><span><ShieldCheck size={15} />Your profile, your control</span></header>
      <main className="onboarding-main">
        <div className="onboarding-intro">
          {editing ? (
            <>
              <span className="eyebrow">MY PROFILE</span>
              <h1>Your details<span className="lime-period">.</span></h1>
              <p>The agent only uses details you have confirmed. Edit anything, then confirm again on the last step.</p>
              <span className={`status-chip ${p.confirmed ? 'ok' : ''}`}>{p.confirmed ? <><Check size={14} />Confirmed</> : <><Pencil size={14} />Changes not confirmed yet</>}</span>
            </>
          ) : (
            <>
              <span className="eyebrow">FIRST, LET’S GET TO KNOW YOU</span>
              <h1>Your next chapter starts with you<span className="lime-period">.</span></h1>
              <p>Add the basics and your resume. We’ll fill what we can; you review the rest.</p>
            </>
          )}
        </div>
        <div className="onboarding-progress">
          {steps.map((s, i) => (
            <button key={s} className={`${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`} aria-current={i === step ? 'step' : undefined}
              onClick={() => { if (i < step || editing) go(i); }}><span>{i < step ? <Check size={15} /> : i + 1}</span><b>{s}</b></button>
          ))}
        </div>
        <section className="panel onboarding-form" ref={formRef}>
          <div className="onboarding-section-head">
            <div><span className="eyebrow">STEP {step + 1} OF 5</span><h2>{steps[step]}</h2></div>
            <span>{step === 4 ? 'One final check' : 'Saved as you continue'}</span>
          </div>
          {tidied.length > 0 && step === 0 && <div className="info-box"><AlertCircle size={18} /><div>{tidied.map(t => <p key={t}>{t}</p>)}</div></div>}
          {error && <div className="error-banner form-error" role="alert"><AlertCircle size={17} /><span>{error}</span></div>}

          {step === 0 && <>
            <div className="form-grid">
              <Field label="Full name" required hint="As it appears on your resume." note={suggested('name')} error={err('name')}>
                {a => <input {...a} autoComplete="name" placeholder="e.g. Priya Sharma" value={p.name} onChange={e => set({name: e.target.value})} />}
              </Field>
              <Field label="Email address" required hint="Applications and replies use this address." note={suggested('email')} error={err('email')}>
                {a => <input {...a} type="email" autoComplete="email" inputMode="email" placeholder="name@example.com" value={p.email} onChange={e => set({email: e.target.value})} />}
              </Field>
              <Field label="Mobile number" required hint="Choose the country code, then enter the number without it." note={suggested('phone')} error={err('phone')}>
                {a => (
                  <div className="phone-row">
                    <select aria-label="Country code" value={phone.code} onChange={e => set({phone: L.joinPhone(e.target.value, phone.number)})}>
                      {L.PHONE_CODES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                    </select>
                    <input {...a} type="tel" autoComplete="tel-national" inputMode="tel" placeholder="98765 43210" value={phone.number} onChange={e => set({phone: L.joinPhone(phone.code, e.target.value)})} />
                  </div>
                )}
              </Field>
              <Field label="Portfolio URL" optional hint="Starts with https://" note={suggested('portfolio')} error={err('portfolio')}>
                {a => <input {...a} type="url" inputMode="url" autoComplete="url" placeholder="https://linkedin.com/in/your-name" value={p.portfolio} onChange={e => set({portfolio: e.target.value})} />}
              </Field>
            </div>
            <Field label="Address" required hint="Street, city, state and postal code. Used only when an application asks for it." error={err('address')}>
              {a => <textarea {...a} rows={3} autoComplete="street-address" placeholder={'12 MG Road, Madhapur\nHyderabad, Telangana 500081'} value={p.address} onChange={e => set({address: e.target.value})} />}
            </Field>
            <div className={`upload-block ${err('resume_text') ? 'has-error' : ''}`} data-error={err('resume_text') ? 'true' : undefined}>
              <label className="upload-zone"><Upload size={26} /><b>{busy ? 'Reading your document…' : p.resume_filename || 'Upload your resume / CV'}</b><span>PDF, DOCX or TXT · up to 5 MB</span>
                <input disabled={busy} type="file" accept=".pdf,.docx,.txt" onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ''; }} />
              </label>
              {err('resume_text') && <p className="pf-error" role="alert"><AlertCircle size={14} />{err('resume_text')}</p>}
            </div>
            {p.resume_text && <div className="extraction-summary"><Check size={18} /><div><b>Resume text is ready to review</b><p>{extracted.length ? `${extracted.length} profile fields recognized. Existing details were preserved.` : 'Review the text below. Add any missing information in the next steps.'}</p>{notes.map(n => <small key={n}>{n}</small>)}</div></div>}
            <details className="resume-text"><summary><FileText size={17} />Review or paste resume text</summary>
              <Field label="Resume text" required hint="Used to tailor each application. Paste it here if you cannot upload a file." error={err('resume_text')}>
                {a => <textarea {...a} rows={10} value={p.resume_text} onChange={e => set({resume_text: e.target.value})} />}
              </Field>
            </details>
          </>}

          {step === 1 && <>
            <ChoiceCards legend="Which describes you best?" required value={p.career_level} error={err('career_level')}
              onChange={value => set({career_level: value, no_experience: value === 'Experienced' ? false : !p.work_history.length})}
              options={[{value: 'Intern', title: 'Intern', text: 'Looking for an internship'}, {value: 'Fresher', title: 'Fresher', text: 'Recent graduate looking for a first full-time role'}, {value: 'Experienced', title: 'Experienced', text: 'I have professional work experience'}]} />
            <p className="stage-help">This decides which jobs the agent looks for and which experience levels it searches.</p>
            {p.career_level === 'Experienced' && (
              <div className="form-grid one">
                <Field label="Total years of professional experience" required error={err('experience')}>
                  {a => <input {...a} type="number" inputMode="decimal" min={0} max={70} step={0.5} placeholder="e.g. 3" value={p.experience || ''} onChange={e => set({experience: e.target.value === '' ? 0 : Number(e.target.value)})} />}
                </Field>
              </div>
            )}
            <div className="repeat-heading"><h3>Education</h3><button type="button" className="text-button" onClick={() => set({education: [...p.education, {...emptyEducation}]})}><Plus size={16} />Add education</button></div>
            {!p.education.length && <p className={`missing-note ${err('education') ? 'is-error' : ''}`} data-error={err('education') ? 'true' : undefined}>{err('education') || 'No education added yet. Add your school and qualification.'}</p>}
            {p.education.map((row, i) => (
              <div className="repeat-card" key={i}>
                <div className="repeat-title"><b>Education {i + 1}</b><button type="button" className="icon-button" aria-label={`Remove education ${i + 1}`} onClick={() => set({education: p.education.filter((_, n) => n !== i)})}><Trash2 size={16} /></button></div>
                <div className="form-grid">
                  <Field label="Degree" required error={err(`education.${i}.degree`)}>{a => <PSelect props={a} value={row.degree} onChange={v => setEducation(i, {degree: v})} options={L.DEGREES} placeholder="Choose a degree" />}</Field>
                  <Field label="School or college" required error={err(`education.${i}.school`)}>{a => <input {...a} autoComplete="organization" placeholder="e.g. Mallareddy University" value={row.school} onChange={e => setEducation(i, {school: e.target.value})} />}</Field>
                  <Field label="Field of study" required error={err(`education.${i}.major`)}>{a => <input {...a} placeholder="e.g. Computer Science" value={row.major} onChange={e => setEducation(i, {major: e.target.value})} />}</Field>
                  <Field label="Graduation year" required hint="Expected year if you are still studying." error={err(`education.${i}.year`)}>{a => <PSelect props={a} value={row.year} onChange={v => setEducation(i, {year: v})} options={L.graduationYears(new Date())} placeholder="Choose a year" />}</Field>
                </div>
              </div>
            ))}
            <div className="repeat-heading"><h3>Work experience</h3><button type="button" className="text-button" onClick={() => set({work_history: [...p.work_history, {...emptyWork}], no_experience: false})}><Plus size={16} />Add experience</button></div>
            {p.career_level && p.career_level !== 'Experienced' && !p.work_history.length && <p className="stage-help">No professional experience needed. You can still add internships or projects with “Add experience”.</p>}
            {err('work_history') && <p className="missing-note is-error" data-error="true">{err('work_history')}</p>}
            {p.work_history.map((row, i) => (
              <div className="repeat-card" key={i}>
                <div className="repeat-title"><b>Experience {i + 1}</b><button type="button" className="icon-button" aria-label={`Remove experience ${i + 1}`} onClick={() => set({work_history: p.work_history.filter((_, n) => n !== i)})}><Trash2 size={16} /></button></div>
                <div className="form-grid">
                  <Field label="Job title" required error={err(`work.${i}.title`)}>{a => <input {...a} placeholder="e.g. Software Intern" value={row.title} onChange={e => setWork(i, {title: e.target.value})} />}</Field>
                  <Field label="Company" required error={err(`work.${i}.company`)}>{a => <input {...a} autoComplete="organization" placeholder="e.g. Acme Technologies" value={row.company} onChange={e => setWork(i, {company: e.target.value})} />}</Field>
                  <Field label="Start month" required error={err(`work.${i}.start`)}>{a => <input {...a} type="month" value={monthOf(row.start)} onChange={e => setWork(i, {start: e.target.value ? `${e.target.value}-01` : ''})} />}</Field>
                  <Field label="End month" required={!row.current} error={err(`work.${i}.end`)}>{a => <input {...a} type="month" disabled={row.current} value={monthOf(row.end)} onChange={e => setWork(i, {end: e.target.value ? `${e.target.value}-01` : ''})} />}</Field>
                </div>
                <label className="check-label"><input type="checkbox" checked={row.current} onChange={e => setWork(i, {current: e.target.checked, end: e.target.checked ? '' : row.end})} />I currently work here</label>
                <Field label="What you did" required hint="Two or three lines: your responsibilities and achievements." error={err(`work.${i}.responsibilities`)}>{a => <textarea {...a} rows={4} value={row.responsibilities} onChange={e => setWork(i, {responsibilities: e.target.value})} />}</Field>
              </div>
            ))}
          </>}

          {step === 2 && <>
            <div className="form-grid">
              <Field label="Positions you want" required hint="Press Enter after each one." error={err('roles')} className="span-2">
                {a => <TagInput props={a} values={L.splitList(p.roles)} onChange={v => set({roles: L.joinList(v)})} suggestions={L.ROLE_SUGGESTIONS} placeholder="e.g. AI Engineer" />}
              </Field>
              <Field label="Target country" required hint="Where you want to work. Jobs elsewhere are skipped." error={err('country')}>
                {a => <PSelect props={a} value={country} placeholder="Choose a country" options={[]} groups={[{label: 'Popular', options: L.TOP_COUNTRIES}, {label: 'All countries', options: L.COUNTRIES}]}
                  onChange={v => set({country: v, currency: !p.salary ? L.defaultCurrency(v) : p.currency})} />}
              </Field>
              <Field label="Preferred cities" required hint="Add “Remote” if you are open to remote jobs. Pick a suggestion to use a confirmed place." error={err('locations')}>
                {a => <TagInput props={a} values={L.splitList(p.locations)} onChange={v => set({locations: L.joinList(v)})} suggestions={L.citySuggestions(country)} liveSuggestions={lookupCities} placeholder="e.g. Hyderabad" />}
              </Field>
              <Field label="Employment type" required error={err('employment_type')}>{a => <PSelect props={a} value={p.employment_type} onChange={v => set({employment_type: v})} options={['Full-time', 'Part-time', 'Contract', 'Internship', 'Temporary']} />}</Field>
              <Field label="When can you start?" required error={err('availability')}>
                {a => (
                  <div className="stack">
                    <PSelect props={a} value={L.START_OPTIONS.includes(p.availability) ? p.availability : startIsDate ? '__date' : ''}
                      onChange={v => set({availability: v === '__date' ? todayIso() : v})} options={[...L.START_OPTIONS, ['__date', 'Pick a date…']]} />
                    {startIsDate && <input type="date" aria-label="Start date" min={todayIso()} value={p.availability} onChange={e => set({availability: e.target.value})} />}
                  </div>
                )}
              </Field>
              <Field label="Willing to relocate?" required error={err('relocation')}>{a => <PSelect props={a} value={p.relocation} onChange={v => set({relocation: v})} options={['Yes', 'No', 'Open to discussion']} />}</Field>
              <Field label="Preferred work mode" required error={err('work_modes')}>
                {() => (
                  <div className="mode-choices" role="group" aria-label="Preferred work mode">
                    {['Remote', 'Hybrid', 'Onsite'].map(m => (
                      <button type="button" key={m} aria-pressed={p.work_modes.includes(m)} className={p.work_modes.includes(m) ? 'selected' : ''}
                        onClick={() => set({work_modes: p.work_modes.includes(m) ? p.work_modes.filter(x => x !== m) : [...p.work_modes, m]})}>{p.work_modes.includes(m) && <Check size={15} />} {m}</button>
                    ))}
                  </div>
                )}
              </Field>
            </div>
            <Field label="Expected salary" optional hint="Used only to answer application questions. It never filters jobs." error={err('salary')}>
              {a => (
                <div className="salary-row">
                  <select aria-label="Currency" value={p.currency} onChange={e => set({currency: e.target.value})}>{L.CURRENCIES.map(([code, name]) => <option key={code} value={code}>{code} · {name}</option>)}</select>
                  <input {...a} inputMode="numeric" placeholder="e.g. 50000" value={p.salary} onChange={e => set({salary: e.target.value.replace(/[^\d.]/g, '')})} />
                  <select aria-label="Per" value={p.pay_period} onChange={e => set({pay_period: e.target.value})}><option value="month">per month</option><option value="year">per year</option><option value="hour">per hour</option></select>
                </div>
              )}
            </Field>
            <Field label="Skills" required hint="Add the years next to a skill so the agent can answer “years of experience” questions truthfully. Skills without years are never answered for you." error={err('skills')}>
              {a => <SkillsEditor props={a} skills={skillList} years={p.skill_years || {}} suggestions={L.SKILL_SUGGESTIONS}
                onChange={(skills, years) => set({skills: L.joinList(skills), skill_years: years})} />}
            </Field>
            <div className="rules-box">
              <h3>How strictly to match</h3>
              <label className="check-label"><input type="checkbox" checked={p.strict_country} onChange={e => set({strict_country: e.target.checked, strict_location: e.target.checked ? p.strict_location : false})} /><span><b>Only jobs in my target country</b><small>Turn this off if you're open to relocating or working remotely for a company anywhere. Your target country above still answers work-authorization and currency questions.</small></span></label>
              <label className="check-label"><input type="checkbox" checked={p.strict_location} disabled={!p.strict_country} onChange={e => set({strict_location: e.target.checked})} /><span><b>Only my preferred cities</b><small>{p.strict_country ? 'Turn this off to see jobs in any city of your target country.' : "Not applicable — you're open to any country, so any city follows."}</small></span></label>
              <label className="check-label"><input type="checkbox" checked={p.strict_mode} onChange={e => set({strict_mode: e.target.checked})} /><span><b>Only my chosen work modes</b><small>For example, skip onsite jobs if you chose Remote and Hybrid.</small></span></label>
            </div>
          </>}

          {step === 3 && <>
            {atHome ? (
              <>
                <div className="home-auth"><ShieldCheck size={19} /><div><b>Work authorization: Indian citizen, no visa sponsorship needed</b><p>Filled in automatically because you are looking for jobs in India. The agent will answer these application questions for you.</p></div>
                  <button type="button" className="text-button link" onClick={() => setAskAuth(true)}>I’m not an Indian citizen</button></div>
                <div className="form-grid one">
                  <Field label="Notice period" optional hint="How soon you could join." error={err('notice')}>{a => <PSelect props={a} value={p.notice} onChange={v => set({notice: v})} options={L.NOTICE_PERIODS} />}</Field>
                </div>
              </>
            ) : (
              <>
                <div className="form-grid">
                  <Field label={`Your work status in ${country || 'the target country'}`} required error={err('eligibility')}>{a => <PSelect props={a} value={p.eligibility} onChange={v => set({eligibility: v})} options={L.ELIGIBILITY} />}</Field>
                  <Field label="Notice period" optional hint="How soon you could join." error={err('notice')}>{a => <PSelect props={a} value={p.notice} onChange={v => set({notice: v})} options={L.NOTICE_PERIODS} />}</Field>
                </div>
                <ChoiceCards legend={`Will you now or in the future need visa sponsorship to work in ${country || 'this country'}?`} required value={p.sponsorship} error={err('sponsorship')} onChange={v => set({sponsorship: v})}
                  options={[{value: 'No', title: 'No', text: `I can work in ${country || 'this country'} without an employer sponsoring a visa`}, {value: 'Yes', title: 'Yes', text: 'I would need an employer to sponsor my work visa'}]} />
                {warning && <div className="banner-warn" role="status"><AlertCircle size={17} />{warning}</div>}
                <Field label="Work authorization statement" required hint="Filled in from your answers above. Edit it if you need to be more specific." error={err('authorization')}>
                  {a => <input {...a} value={p.authorization} onChange={e => set({authorization: e.target.value})} />}
                </Field>
                {country === 'India' && <button type="button" className="text-button link" onClick={() => { setAskAuth(false); setP(old => ({...old, eligibility: 'Citizen', sponsorship: 'No', authorization: L.authorizationText('Citizen', 'India')})); }}>I am an Indian citizen: fill this in for me</button>}
              </>
            )}
            <div className={`pf ${err('age_confirmed') ? 'has-error' : ''}`} data-error={err('age_confirmed') ? 'true' : undefined}>
              <label className="check-label agree"><input type="checkbox" checked={p.age_confirmed} aria-invalid={!!err('age_confirmed')} onChange={e => set({age_confirmed: e.target.checked})} />I meet the legal minimum working age in my target country.</label>
              {err('age_confirmed') && <p className="pf-error" role="alert"><AlertCircle size={14} aria-hidden="true" />{err('age_confirmed')}</p>}
            </div>
            <div className="repeat-heading"><h3>Common application questions</h3></div>
            <p className="stage-help">Employers ask these again and again. Answer once and the agent uses your answer. If you leave one unanswered, the agent skips any job that asks it, because it never guesses about you.</p>
            <div className="common-questions">
              {L.COMMON_QUESTIONS.map(q => {
                const value = common[q.id] || '';
                return (
                  <div className="common-row" key={q.id}>
                    <span id={`cq-${q.id}`}>{q.question}</span>
                    <div className="yn" role="radiogroup" aria-labelledby={`cq-${q.id}`}>
                      {(['Yes', 'No', ''] as const).map(option => (
                        <button type="button" key={option || 'unset'} role="radio" aria-checked={value === option} className={value === option ? 'selected' : ''} onClick={() => set({screening: L.setCommonAnswer(p.screening, q.id, option)})}>{option || 'Not set'}</button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="repeat-heading"><h3>Documents and reusable answers</h3></div>
            <Field label="Cover letter" optional hint="Used as a starting point when the agent writes tailored letters.">
              {a => <textarea {...a} rows={4} value={p.cover_letter_text} onChange={e => set({cover_letter_text: e.target.value})} />}
            </Field>
            <label className="cover-upload"><Upload size={16} />Or upload a cover letter<input type="file" disabled={busy} accept=".pdf,.docx,.txt" onChange={e => { const f = e.target.files?.[0]; if (f) upload(f, true); e.target.value = ''; }} /></label>
            <Field label="Approved answers to common questions" optional hint="One per line, like “Are you comfortable with night shifts? Yes”. The agent uses only what you write here.">
              {a => <textarea {...a} rows={4} value={p.screening} onChange={e => set({screening: e.target.value})} />}
            </Field>
            <Field label="Companies to exclude" optional hint="The agent will skip these employers.">
              {a => <TagInput props={a} values={L.splitList(p.excluded_companies)} onChange={v => set({excluded_companies: L.joinList(v)})} placeholder="Type a company and press Enter" />}
            </Field>
            <details className="demographics"><summary>Optional equal-opportunity answers</summary>
              <p>These are never guessed from your resume. Answer only what you want to share; “Prefer not to say” is always fine.</p>
              <div className="form-grid">
                <Field label="Gender">{a => <PSelect props={a} value={p.eeo_gender} onChange={v => set({eeo_gender: v})} options={['Prefer not to say', 'Woman', 'Man', 'Non-binary', 'Self-describe']} />}</Field>
                <Field label="Race or ethnicity">{a => <PSelect props={a} value={p.eeo_ethnicity} onChange={v => set({eeo_ethnicity: v})} options={['Prefer not to say', 'Asian', 'Black / African descent', 'Hispanic / Latino', 'White', 'Indigenous', 'Mixed / multiple', 'Other']} />}</Field>
                <Field label="Disability status">{a => <PSelect props={a} value={p.eeo_disability} onChange={v => set({eeo_disability: v})} options={['Prefer not to say', 'Yes', 'No']} />}</Field>
                <Field label="Veteran status">{a => <PSelect props={a} value={p.eeo_veteran} onChange={v => set({eeo_veteran: v})} options={['Prefer not to say', 'Yes', 'No']} />}</Field>
              </div>
            </details>
          </>}

          {step === 4 && <>
            {issues.length > 0 && (
              <div className="issue-box" role="alert">
                <b><AlertCircle size={17} />Fix these before you confirm</b>
                <ul>{issues.flatMap(({step: s, errors: e}) => Object.entries(e).slice(0, 4).map(([key, message]) => (
                  <li key={s + key}><button type="button" onClick={() => go(s)}>{steps[s]}</button><span>{message}</span></li>
                )))}</ul>
              </div>
            )}
            <div className="review-cards">
              <ReviewCard title="Contact" onEdit={() => go(0)} rows={[['Name', p.name], ['Email', p.email], ['Mobile', p.phone], ['Address', p.address], ['Resume', p.resume_filename || (p.resume_text ? 'Resume text provided' : '')]]} />
              <ReviewCard title="Career and education" onEdit={() => go(1)} rows={[['Stage', p.career_level], ['Education', p.education.map(e => `${e.degree}, ${e.major} · ${e.school} (${e.year})`).join('\n')], ['Experience', p.work_history.length ? p.work_history.map(w => `${w.title} at ${w.company}`).join('\n') : 'No professional experience yet']]} />
              <ReviewCard title="Job preferences" onEdit={() => go(2)} rows={[['Positions', L.splitList(p.roles).join(', ')], ['Where', `${L.splitList(p.locations).join(', ')} · ${country || p.country}`], ['Work mode', p.work_modes.join(', ')], ['Start', p.availability], ['Salary', p.salary ? `${p.currency} ${p.salary} per ${p.pay_period}` : 'Not specified']]} />
              <ReviewCard title="Skills" onEdit={() => go(2)} rows={[[`${skillList.length} skills`, skillList.slice(0, 14).map(s => (p.skill_years?.[s] !== undefined ? `${s} (${p.skill_years[s]}y)` : s)).join(', ') + (skillList.length > 14 ? ` and ${skillList.length - 14} more` : '')]]} />
              <ReviewCard title="Eligibility" onEdit={() => go(3)} rows={[['Status', p.eligibility], ['Sponsorship needed', p.sponsorship], ['Statement', p.authorization], ['Notice period', p.notice || 'Not specified']]} />
            </div>
            <label className={`check-label agree ${issues.length ? 'disabled' : ''}`}><input type="checkbox" disabled={issues.length > 0} checked={p.confirmed} onChange={e => setP({...p, confirmed: e.target.checked})} />I reviewed my details and confirm they are accurate.</label>
            <div className="info-box"><ShieldCheck size={19} /><p>You can update your profile later. The agent uses only confirmed details, and asks you when an answer is missing.</p></div>
          </>}

          <div className="form-footer">
            <button type="button" className="btn ghost" disabled={step === 0 || busy} onClick={() => go(step - 1)}><ArrowLeft size={16} />Back</button>
            <button type="button" className="btn primary" disabled={busy} onClick={next}>{busy ? <LoaderCircle size={17} className="spin" /> : step === 4 ? 'Confirm and open dashboard' : 'Save and continue'}<ArrowRight size={17} /></button>
          </div>
        </section>
      </main>
      <footer className="onboarding-footer">Your information builds better applications. You stay in control.</footer>
    </div>
  );
}

function ReviewCard({title, rows, onEdit}: {title: string; rows: [string, string][]; onEdit: () => void}) {
  return (
    <section className="review-card">
      <div className="review-card-head"><h3>{title}</h3><button type="button" className="text-button" onClick={onEdit}><Pencil size={14} />Edit</button></div>
      <dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd className={value ? '' : 'empty-value'}>{value || 'Not provided'}</dd></div>)}</dl>
    </section>
  );
}
