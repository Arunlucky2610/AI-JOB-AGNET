'use client';
import {useId, useState, useEffect, type ReactNode} from 'react';
import {X, Plus, AlertCircle, MapPin} from 'lucide-react';
import {parseSkillList, splitList} from './profile-logic';

type ControlProps = {id: string; 'aria-invalid': boolean; 'aria-describedby'?: string};

/** One labelled control with a hint underneath and its own error message. `children` receives the accessibility props to spread on the input. */
export function Field({label, required, optional, hint, note, error, children, className = ''}: {label: string; required?: boolean; optional?: boolean; hint?: string; note?: string; error?: string; children: (props: ControlProps) => ReactNode; className?: string}) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ') || undefined;
  return (
    <div className={`pf ${error ? 'has-error' : ''} ${className}`} data-error={error ? 'true' : undefined}>
      <label htmlFor={id}>
        {label}
        {required && <span className="pf-req" aria-hidden="true">*</span>}
        {required && <span className="sr-only"> (required)</span>}
        {optional && <span className="pf-optional">Optional</span>}
      </label>
      {children({id, 'aria-invalid': !!error, 'aria-describedby': describedBy})}
      {hint && !error && <p className="pf-hint" id={`${id}-hint`}>{hint}</p>}
      {note && !error && <p className="pf-note">{note}</p>}
      {error && <p className="pf-error" id={`${id}-error`} role="alert"><AlertCircle size={14} aria-hidden="true" />{error}</p>}
    </div>
  );
}

/** Pick one of a few options shown as cards, for choices that need a sentence of explanation. */
export function ChoiceCards({legend, options, value, onChange, error, required}: {legend: string; options: {value: string; title: string; text: string}[]; value: string; onChange: (value: string) => void; error?: string; required?: boolean}) {
  const id = useId();
  return (
    <fieldset className={`pf choice-set ${error ? 'has-error' : ''}`} data-error={error ? 'true' : undefined} aria-describedby={error ? `${id}-error` : undefined}>
      <legend>{legend}{required && <span className="pf-req" aria-hidden="true">*</span>}</legend>
      <div className="choice-cards" role="radiogroup" aria-label={legend}>
        {options.map(option => (
          <button type="button" key={option.value} role="radio" aria-checked={value === option.value} className={`choice-card ${value === option.value ? 'selected' : ''}`} onClick={() => onChange(option.value)}>
            <b>{option.title}</b><span>{option.text}</span>
          </button>
        ))}
      </div>
      {error && <p className="pf-error" id={`${id}-error`} role="alert"><AlertCircle size={14} aria-hidden="true" />{error}</p>}
    </fieldset>
  );
}

/** Type and press Enter (or comma) to add; click a suggestion; backspace removes the last. Pasted lists are split. */
/** `liveSuggestions`, when given, looks up real confirmed places as the person types (debounced); once
 * they've typed something, only its results are offered, in place of the static list, so a suggestion is
 * always a real place, never a guess. Each result's `label` (e.g. "Bengaluru, Karnataka, India") is shown
 * so a same-named place elsewhere is never picked by mistake, but only its `value` (e.g. "Bengaluru") is
 * stored — values here are joined into one comma list, so a value with its own commas would come apart on
 * the next read. Free text is still accepted on Enter, comma or blur either way — this narrows what's
 * suggested, it never blocks what someone can add. */
export function TagInput({values, onChange, suggestions = [], liveSuggestions, placeholder, props}: {values: string[]; onChange: (values: string[]) => void; suggestions?: string[]; liveSuggestions?: (query: string) => Promise<{label: string; value: string}[]>; placeholder?: string; props: ControlProps}) {
  const [text, setText] = useState('');
  const [live, setLive] = useState<{label: string; value: string}[] | null>(null);
  const has = (item: string) => values.some(v => v.toLowerCase() === item.toLowerCase());
  const add = (raw: string) => {
    const items = splitList(raw).filter(item => !has(item));
    if (items.length) onChange([...values, ...items]);
    setText(''); setLive(null);
  };
  const choose = (item: string) => { if (!has(item)) onChange([...values, item]); setText(''); setLive(null); };
  useEffect(() => {
    if (!liveSuggestions || !text.trim()) { setLive(null); return; }
    let current = true;
    const timer = setTimeout(() => {
      liveSuggestions(text.trim()).then(found => { if (current) setLive(found); }).catch(() => { if (current) setLive([]); });
    }, 300);
    return () => { current = false; clearTimeout(timer); };
  }, [text, liveSuggestions]);
  const searching = !!liveSuggestions && text.trim().length > 0;
  const candidates = searching ? live ?? [] : suggestions.map(s => ({label: s, value: s})).filter(s => s.label.toLowerCase().includes(text.trim().toLowerCase()));
  const seenValues = new Set<string>();
  // Two confirmed places can share a value (Hyderabad, India and Hyderabad, Pakistan both store as
  // "Hyderabad"); once one is offered, a second that would store the same thing adds nothing.
  const open = candidates.filter(s => !has(s.value) && !seenValues.has(s.value.toLowerCase()) && seenValues.add(s.value.toLowerCase())).slice(0, 8);
  return (
    <div>
      <div className={`tag-box ${props['aria-invalid'] ? 'invalid' : ''}`}>
        {values.map(value => (
          <span className="tag-chip" key={value}>{value}<button type="button" aria-label={`Remove ${value}`} onClick={() => onChange(values.filter(v => v !== value))}><X size={13} /></button></span>
        ))}
        <input {...props} className="tag-text" value={text} placeholder={values.length ? '' : placeholder}
          onChange={e => { const v = e.target.value; if (v.endsWith(',')) add(v); else setText(v); }}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); if (text.trim()) add(text); } else if (e.key === 'Backspace' && !text && values.length) onChange(values.slice(0, -1)); }}
          onBlur={() => { if (text.trim()) add(text); }}
          onPaste={e => { const pasted = e.clipboardData.getData('text'); if (/[,;\n|]/.test(pasted)) { e.preventDefault(); add(pasted); } }} />
      </div>
      {open.length > 0 && (
        <div className="tag-suggest" aria-label={searching ? 'Confirmed places' : 'Suggestions'}>
          {open.map(s => <button type="button" key={s.value} onMouseDown={e => e.preventDefault()} onClick={() => choose(s.value)}>{searching ? <MapPin size={12} /> : <Plus size={12} />}{s.label}</button>)}
        </div>
      )}
    </div>
  );
}

/** Skills as chips, each with its own years of experience. One place for both the skills list and the per-skill years. */
export function SkillsEditor({skills, years, onChange, suggestions, props}: {skills: string[]; years: Record<string, number>; onChange: (skills: string[], years: Record<string, number>) => void; suggestions: string[]; props: ControlProps}) {
  const [text, setText] = useState('');
  const has = (item: string) => skills.some(s => s.toLowerCase() === item.toLowerCase());
  const add = (raw: string) => {
    const items = parseSkillList(raw).filter(item => !has(item));
    if (items.length) onChange([...skills, ...items], years);
    setText('');
  };
  const remove = (skill: string) => { const rest = {...years}; delete rest[skill]; onChange(skills.filter(s => s !== skill), rest); };
  const setYears = (skill: string, value: string) => {
    const next = {...years};
    if (value === '') delete next[skill]; else next[skill] = Math.max(0, Math.min(70, Number(value)));
    onChange(skills, next);
  };
  const open = suggestions.filter(s => !has(s) && s.toLowerCase().includes(text.trim().toLowerCase())).slice(0, 10);
  const counted = skills.filter(s => years[s] !== undefined).length;
  return (
    <div className="skills-editor">
      <div className={`tag-box ${props['aria-invalid'] ? 'invalid' : ''}`}>
        <input {...props} className="tag-text" value={text} placeholder="Type a skill and press Enter, or paste a list"
          onChange={e => { const v = e.target.value; if (v.endsWith(',')) add(v); else setText(v); }}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); if (text.trim()) add(text); } }}
          onBlur={() => { if (text.trim()) add(text); }}
          onPaste={e => { const pasted = e.clipboardData.getData('text'); if (/[,;\n|]/.test(pasted)) { e.preventDefault(); add(pasted); } }} />
      </div>
      {open.length > 0 && <div className="tag-suggest" aria-label="Suggestions">{open.map(s => <button type="button" key={s} onClick={() => add(s)}><Plus size={12} />{s}</button>)}</div>}
      {skills.length > 0 && (
        <>
          <div className="skills-meta"><span>{skills.length} skills · {counted} with years</span><button type="button" className="text-button" onClick={() => onChange([], {})}>Clear all</button></div>
          <ul className="skills-grid">
            {skills.map(skill => (
              <li className="skill-chip" key={skill}>
                <span className="skill-name" title={skill}>{skill}</span>
                <input type="number" inputMode="decimal" min={0} max={70} step={0.5} placeholder="yrs" aria-label={`Years of experience with ${skill}`} value={years[skill] ?? ''} onChange={e => setYears(skill, e.target.value)} />
                <button type="button" aria-label={`Remove ${skill}`} onClick={() => remove(skill)}><X size={13} /></button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
