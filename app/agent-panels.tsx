'use client';
import { useEffect, useState } from 'react';
import { 
  CheckCircle2, AlertCircle, ThumbsUp, ThumbsDown, Target, ListOrdered, 
  ShieldCheck, ExternalLink, Search, Filter, Sparkles, FileText, 
  Clock, ChevronDown, ChevronRight, Zap, Award, ArrowUpRight, Check, Briefcase,
  Monitor, KeyRound, Play, RefreshCw, Send, AlertTriangle, Globe, MapPin, Radio,
  Eye, EyeOff, Lock, Trash2, Archive, RotateCcw, HelpCircle, X
} from 'lucide-react';


export type Plan = {objective:{roles:string[];level:string;country:string;locations:string;work_modes:string[];sponsorship:string;blacklist:string[]};searches:string[];threshold:number;quota:{limit:number;used_today:number;waiting:number;slots:number};budget:{usd_limit:number;usd_spent:number};questions:string[];steps:string[]};
export type ShortItem = {job_id:string;title:string;company:string;score:number;global_score:number;status:string;reason?:string;rank_adjust?:number};
type Eval = {folds:{baseline_ap:number;adjusted_ap:number;delta:number}[];mean_delta:number;baseline_ap:number;adjusted_ap:number};
type Proposal = {status:'insufficient_data'|'no_improvement'|'rejected'|'proposed'|'already_active';decided:number;progressed:number;needed?:string;reason?:string;version?:string;adjustments?:Record<string,Record<string,number>>;rationale?:string[];evaluation?:Eval;caveat?:string};
type ActiveRanking = {version:string;rationale:string[];evaluation:Eval;results_used:number;accepted_at:string};
type RankingView = {active:ActiveRanking|null;proposal:Proposal;baseline:string};
export type TraceItem = {time:string;step:string;subject:string;decision:string;reason:string};
export type Outcome = {stage:string;fit_feedback:string|null;note:string};
export type Verification = {status:string;evidence?:string;checked_at?:string;method?:string};
export type Grounding = {ungrounded:string[];confirmed:string[]};
export type Evidence = {confirmation_text?:string;job_id?:string;timestamp?:string;screenshots?:{review?:string;confirmation?:string}};
type Api = <T>(path:string,method?:string,body?:unknown)=>Promise<T>;
export type DiagnosticInfo = {
  category: string;
  headline: string;
  explanation: string;
  recommendation: string;
  raw_event?: string;
  time?: string;
  can_retry?: boolean;
};
type TrackedApp = {
  id: string;
  status: string;
  job: {
    id?: string;
    title: string;
    company: string;
    score?: number;
    verification?: Verification;
    match: { score: number };
    url?: string;
    source?: string;
    archived?: boolean;
  };
  outcome: Outcome | null;
  evidence?: Evidence | null;
  events?: { time: string; text: string }[];
  archived?: boolean;
  diagnostic?: DiagnosticInfo | null;
  updated: string;
};
type Summary = {submitted:number;stages:Record<string,number>;progressed:number;shortlist_rate:number|null;decided_rate:number|null;response_rate:number|null;fit_up:number;fit_down:number;definition:string};
type Group = Record<string,{decided:number;progressed:number;rate:number}>;
type Insights = {ranking:RankingView;buckets:{by_fit_score:Group;by_work_mode:Group;by_experience_asked:Group};threshold_advice:string|null;ranking_test:{enough_data:boolean;decided:number;needed?:string;baseline_ap?:number;candidate_ap?:number;better?:boolean};note:string};

export const STAGE_LABELS:Record<string,string>={waiting:'Waiting to hear',shortlisted:'Shortlisted',assessment:'Assessment',interview:'Interview',offer:'Offer',rejected:'Rejected',no_response:'No response'};
const ITEM_LABELS:Record<string,string>={ranked:'Queued',prepared:'Documents ready',closed:'Closed',uncertain:'Not verified open',duplicate:'Duplicate',over_quota:'Over daily limit',over_budget:'Over budget',error:'Could not prepare'};
const pct=(n:number|null)=>n===null?'—':`${n}%`;

export function VerificationChip({v}:{v?:Verification}){
  if(!v)return null;
  const open=v.status==='open',bad=v.status==='closed'||v.status==='uncertain';
  const label=open?'Verified open':v.status==='closed'?'Closed':v.status==='uncertain'?'Not verified':'Not re-checked yet';
  return <span className={`verify-chip ${open?'ok':bad?'bad':''}`} title={v.evidence||v.method}>{open?<CheckCircle2 size={13}/>:<AlertCircle size={13}/>}{label}{v.checked_at&&open?` · ${new Date(v.checked_at).toLocaleTimeString()}`:''}</span>;
}

const STEP_META = [
  { label: 'Targeted Discovery', icon: Search, tone: 'search-tone' },
  { label: 'Smart Cost Filter', icon: Filter, tone: 'filter-tone' },
  { label: 'AI Semantic Scoring', icon: Sparkles, tone: 'score-tone' },
  { label: 'Best-Match Ranking', icon: Target, tone: 'rank-tone' },
  { label: 'Live Verification', icon: ShieldCheck, tone: 'verify-tone' },
  { label: 'Document Tailoring', icon: FileText, tone: 'doc-tone' },
  { label: 'Approval & Apply', icon: CheckCircle2, tone: 'apply-tone' },
];

export function PlanPanel({plan,spent}:{plan?:Plan|null;spent?:number}){
  if(!plan)return null;
  const o=plan.objective;
  const usedBudget = spent ?? plan.budget.usd_spent;
  const budgetPct = Math.min(100, Math.round((usedBudget / Math.max(0.01, plan.budget.usd_limit)) * 100));

  return (
    <section className="panel modern-plan-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow-chip"><Zap size={13}/> AUTONOMOUS WORKFLOW PIPELINE</div>
          <h2>Agent Operational Plan & Multi-Stage Pipeline</h2>
          <p>Real-time execution parameters and systematic 7-stage application lifecycle</p>
        </div>
        <span className="pipeline-pill">7-Stage Pipeline Active</span>
      </div>

      <div className="modern-plan-grid">
        <div className="plan-card">
          <div className="plan-card-head">
            <span className="card-badge"><Search size={14}/> TARGET SEARCH</span>
          </div>
          <b>{o.roles.join(', ') || 'Any Role'}</b>
          <p>{o.level} · {o.country}{o.locations ? ` · ${o.locations}` : ''}</p>
          <div className="work-modes-pills">
            {o.work_modes.map(m => <span key={m}>{m}</span>)}
          </div>
        </div>

        <div className="plan-card">
          <div className="plan-card-head">
            <span className="card-badge"><Sparkles size={14}/> AI FIT THRESHOLD</span>
          </div>
          <div className="threshold-display">
            <strong>{plan.threshold}%</strong>
            <span>minimum match</span>
          </div>
          <div className="mini-progress-bar">
            <div style={{ width: `${plan.threshold}%` }} />
          </div>
          <small>Strict semantic relevance score</small>
        </div>

        <div className="plan-card">
          <div className="plan-card-head">
            <span className="card-badge"><Target size={14}/> TODAY’S QUOTA</span>
          </div>
          <div className="quota-display">
            <strong>{plan.quota.slots}</strong>
            <span>to prepare</span>
          </div>
          <p>{plan.quota.used_today} sent · {plan.quota.waiting} waiting · daily limit {plan.quota.limit}</p>
        </div>

        <div className="plan-card">
          <div className="plan-card-head">
            <span className="card-badge"><Clock size={14}/> MODEL BUDGET</span>
          </div>
          <div className="budget-display">
            <strong>${usedBudget.toFixed(2)}</strong>
            <span>/ ${plan.budget.usd_limit.toFixed(2)}</span>
          </div>
          <div className="mini-progress-bar">
            <div style={{ width: `${budgetPct}%`, background: budgetPct > 80 ? '#e67e22' : 'var(--lime)' }} />
          </div>
          <small>{budgetPct}% budget used</small>
        </div>
      </div>

      {o.blacklist.length > 0 && (
        <div className="plan-alert-box blacklist">
          <ShieldCheck size={16}/>
          <span>Excluded companies: <b>{o.blacklist.join(', ')}</b></span>
        </div>
      )}

      {plan.questions.length > 0 && (
        <div className="plan-alert-box info">
          <AlertCircle size={16}/>
          <div>
            <b>The agent needs answers to improve targeting:</b>
            <ul>{plan.questions.map(q => <li key={q}>{q}</li>)}</ul>
          </div>
        </div>
      )}
    </section>
  );
}

export function ShortlistPanel({items,version}:{items?:ShortItem[];version?:string|null}){
  if(!items||!items.length)return null;
  return (
    <section className="panel modern-shortlist-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow-chip"><Award size={13}/> SHORTLISTED OPPORTUNITIES</div>
          <h2>Best Matches First ({items.length})</h2>
          <p>{version&&version!=='baseline'?`Optimized with verified ranking ${version}. `:'Ranked by AI match score & evidence grounding. '}Only candidates within today’s quota advance to document tailoring.</p>
        </div>
        <span className="shortlist-count-badge">{items.length} Evaluated</span>
      </div>

      <div className="shortlist-cards-list">
        {items.map((i, n) => {
          const isReady = i.status === 'prepared';
          const isOverQuota = i.status === 'over_quota';
          return (
            <div className={`modern-rank-card ${i.status}`} key={i.job_id}>
              <div className="rank-number-box">
                <span>{n < 9 ? `0${n + 1}` : n + 1}</span>
              </div>

              <div className="rank-job-info">
                <div className="rank-job-title-row">
                  <h4>{i.title}</h4>
                </div>
                <div className="rank-company-row">
                  <Briefcase size={14}/>
                  <b>{i.company}</b>
                  {i.reason && i.reason !== 'documents ready' && (
                    <span className="rank-reason-pill">{i.reason}</span>
                  )}
                </div>
              </div>

              <div className="rank-meta-actions">
                <div className="score-pill-large">
                  <Sparkles size={14}/>
                  <strong>{i.score}%</strong>
                  <span>Fit</span>
                </div>

                <div className={`status-pill-large ${i.status}`}>
                  {isReady && <Check size={14}/>}
                  {isOverQuota && <Clock size={14}/>}
                  <span>{ITEM_LABELS[i.status] || i.status}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function TracePanel({trace}:{trace?:TraceItem[]}){
  const [open, setOpen] = useState(false);
  if(!trace||!trace.length)return null;

  return (
    <section className="panel modern-trace-panel">
      <button 
        type="button" 
        className="trace-accordion-toggle" 
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <div className="trace-toggle-left">
          <div className="trace-icon-badge">
            <Zap size={16}/>
          </div>
          <div>
            <h3>Decision Audit Trail</h3>
            <p>Verifiable transparent decision reasoning behind each job assessment</p>
          </div>
        </div>
        <div className="trace-toggle-right">
          <span className="decisions-count-pill">{trace.length} Decided Actions</span>
          <ChevronDown size={18} className={`chevron-indicator ${open ? 'rotated' : ''}`}/>
        </div>
      </button>

      {open && (
        <div className="trace-content-body">
          <div className="trace-timeline-list">
            {trace.slice().reverse().map((t, i) => {
              const isPrepared = t.decision === 'prepared';
              const isDefer = t.decision === 'defer';
              const isSkip = t.decision === 'skip' || t.decision === 'drop';
              const decisionClass = isPrepared ? 'prepared' : isDefer ? 'defer' : isSkip ? 'skip' : 'default';

              return (
                <div className={`modern-trace-item ${decisionClass}`} key={i}>
                  <div className="trace-item-marker">
                    <span className="marker-dot"/>
                  </div>
                  <div className="trace-item-body">
                    <div className="trace-item-header">
                      <span className="trace-time-badge"><Clock size={12}/> {new Date(t.time).toLocaleTimeString()}</span>
                      <span className="trace-step-tag">{t.step}</span>
                      <span className={`trace-decision-tag ${decisionClass}`}>{t.decision}</span>
                    </div>
                    <div className="trace-subject-text">
                      <b>{t.subject}</b>
                    </div>
                    {t.reason && (
                      <div className="trace-reason-callout">
                        <small>Rationale:</small> {t.reason}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

/** Claims the profile does not support: the person confirms them (they then count as theirs) or edits them out. */
export function ClaimsPanel({grounding,confirmed,onToggle,editable}:{grounding?:Grounding;confirmed:string[];onToggle:(claim:string)=>void;editable:boolean}){
  const pending=grounding?.ungrounded||[];
  if(!pending.length&&!confirmed.length)return null;
  return <div className="detail-warning claims-box"><b>{pending.length?'Check these claims before approving':'Claims you confirmed'}</b><p>Your profile does not mention these. Remove them from the document, or confirm they are true.</p>
    {[...pending,...confirmed.filter(c=>!pending.includes(c))].map(c=><label className="check-label" key={c}><input type="checkbox" disabled={!editable} checked={confirmed.includes(c)} onChange={()=>onToggle(c)}/>{c}</label>)}</div>;
}

export function EvidenceBlock({id,verification,evidence,status}:{id:string;verification?:Verification;evidence?:Evidence|null;status:string}){
  const shots=evidence?.screenshots||{};
  return <div className="evidence-box"><div><ShieldCheck size={16}/><b>Evidence</b></div>
    <p><VerificationChip v={verification}/>{verification?.evidence&&<small> {verification.evidence}</small>}</p>
    {evidence?.confirmation_text&&<p className="muted">Employer confirmation: “{evidence.confirmation_text}”{evidence.job_id?` · LinkedIn job ${evidence.job_id}`:''}{evidence.timestamp?` · ${new Date(evidence.timestamp).toLocaleString()}`:''}</p>}
    {status==='needs_verification'&&<p className="muted">Submission was attempted but the confirmation was not clearly seen. Check LinkedIn before doing anything else.</p>}
    <div className="evidence-shots">{shots.review&&<a href={`/api/applications/${id}/evidence/review`} target="_blank" rel="noreferrer"><img alt="Form just before submission" src={`/api/applications/${id}/evidence/review`}/><small>Before submitting</small></a>}
      {shots.confirmation&&<a href={`/api/applications/${id}/evidence/confirmation`} target="_blank" rel="noreferrer"><img alt="Confirmation screen" src={`/api/applications/${id}/evidence/confirmation`}/><small>Confirmation</small></a>}</div></div>;
}

function Group({title,group}:{title:string;group:Group}){
  const rows=Object.entries(group);
  if(!rows.length)return null;
  return <div className="bucket"><small>{title}</small>{rows.map(([k,v])=><div key={k}><span>{k}</span><b>{v.rate}%</b><small>{v.progressed} of {v.decided}</small></div>)}</div>;
}

function RankingBlock({view,api,onChange,onError}:{view:RankingView;api:Api;onChange:(r:RankingView)=>void;onError:(m:string)=>void}){
  const p=view.proposal,act=(path:string,body?:unknown)=>api<RankingView>(path,'POST',body).then(onChange).catch(e=>onError(e.message));
  const ev=(e:Eval)=>`on held-out results the order scored ${e.adjusted_ap} versus ${e.baseline_ap} for fit score alone`;
  return <div className="ranking-block"><h3>Ranking</h3>
    {view.active?<div className="info-box vertical"><b>Using your accepted ranking {view.active.version}</b><span>{view.active.rationale.join('; ')}</span><span>Learned from {view.active.results_used} of your recorded results; {ev(view.active.evaluation)}.</span><span>It only reorders jobs that already passed every check. Fit minimum, verification, approval, duplicates and daily limit still apply to every job.</span>
      <button className="btn secondary" onClick={()=>act('/ranking/deactivate')}>Go back to fit score alone</button></div>:<p className="muted">Ranking by fit score alone (the baseline).</p>}
    {p.status==='proposed'&&<div className="info-box vertical"><b>Proposed ranking {p.version}</b>{p.rationale?.map(r=><span key={r}>{r}</span>)}{p.evaluation&&<span>Evidence: {ev(p.evaluation)} (both halves of your {p.decided} results agreed).</span>}<span>{p.caveat}</span>
      <div className="outcome-controls"><button className="btn primary" onClick={()=>act('/ranking/accept',{version:p.version})}>Accept this ranking</button><button className="btn ghost" onClick={()=>act('/ranking/reject',{version:p.version})}>Not now</button></div></div>}
    {p.status==='insufficient_data'&&<p className="muted">No ranking proposal yet: needs {p.needed}; you have {p.decided} results. Nothing is learned from fewer.</p>}
    {p.status==='no_improvement'&&<p className="muted">No proposal: {p.reason}</p>}
    {p.status==='rejected'&&<p className="muted">You declined the current proposal. It returns only if your results change it.</p>}</div>;
}

/** Every application with its verification, evidence and result, plus shortlist conversion and what the recorded results suggest. */
export function TrackerView({
  apps,
  api,
  onReview,
  onControl,
  onRefresh,
  Badge,
  onError
}: {
  apps: TrackedApp[];
  api: Api;
  onReview: (id: string) => void;
  onControl: (id: string, action: string) => void;
  onRefresh?: () => Promise<void>;
  Badge: React.ComponentType<{ status: string }>;
  onError: (m: string) => void;
}) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [filterTab, setFilterTab] = useState<'active' | 'archived' | 'all'>('active');
  const [selectedDiag, setSelectedDiag] = useState<TrackedApp | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const version = apps.map(a => `${a.id}${a.status}${a.outcome?.stage}${a.outcome?.fit_feedback}${a.archived}`).join('|');
  useEffect(() => {
    api<Summary>('/outcomes/summary').then(setSummary).catch(() => {});
    api<Insights>('/outcomes/insights').then(setInsights).catch(() => {});
  }, [version]);

  const save = (id: string, body: Record<string, unknown>) =>
    api(`/applications/${id}/outcome`, 'PUT', body)
      .then(() => api<Summary>('/outcomes/summary').then(setSummary))
      .catch(e => onError(e.message));

  const handleArchive = async (id: string) => {
    try {
      setBusyId(id);
      await api(`/applications/${id}/archive`, 'POST');
      if (onRefresh) await onRefresh();
    } catch (err: any) {
      onError(err?.message || 'Failed to archive application');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id: string, title?: string) => {
    if (!window.confirm(`Delete application for "${title || 'this job'}"? This cannot be undone.`)) return;
    try {
      setBusyId(id);
      await api(`/applications/${id}`, 'DELETE');
      if (onRefresh) await onRefresh();
    } catch (err: any) {
      onError(err?.message || 'Failed to delete application');
    } finally {
      setBusyId(null);
    }
  };

  const [local, setLocal] = useState<Record<string, Outcome>>({});
  const view = (a: TrackedApp): Outcome => local[a.id] || a.outcome || { stage: 'waiting', fit_feedback: null, note: '' };
  const change = (a: TrackedApp, patch: Partial<Outcome>) => {
    setLocal({ ...local, [a.id]: { ...view(a), ...patch } });
    save(a.id, patch);
  };

  const sent = apps.filter(a => a.status === 'submitted');
  const activeApps = apps.filter(a => !a.archived);
  const archivedApps = apps.filter(a => !!a.archived);
  const displayedApps = filterTab === 'active' ? activeApps : filterTab === 'archived' ? archivedApps : apps;

  return <>
    <div className="page-heading">
      <div>
        <span className="eyebrow">KNOW WHAT WORKS</span>
        <h1>Your applications.</h1>
        <p>Every application, its evidence, diagnostic stop reason, and what happened next.</p>
      </div>
    </div>
    <div className="stats-grid">
      {[
        { label: 'Applications sent', value: String(summary?.submitted ?? sent.length), note: 'Confirmed submissions only' },
        { label: 'Shortlist rate', value: pct(summary?.shortlist_rate ?? null), note: `${summary?.progressed ?? 0} progressed of ${summary?.submitted ?? 0} sent` },
        { label: 'Response rate', value: pct(summary?.response_rate ?? null), note: 'Any answer, yes or no' },
        { label: 'Fit feedback', value: `${summary?.fit_up ?? 0} 👍 · ${summary?.fit_down ?? 0} 👎`, note: 'Your own verdicts' }
      ].map(c => (
        <article className="stat neutral" key={c.label}>
          <div><span>{c.label}</span></div>
          <strong>{c.value}</strong>
          <small>{c.note}</small>
        </article>
      ))}
    </div>
    {summary && <p className="muted">{summary.definition}</p>}
    {insights && (
      <section className="panel insights-panel">
        <div className="panel-heading">
          <div>
            <h2>What your results suggest</h2>
            <p>{insights.note}</p>
          </div>
        </div>
        {insights.threshold_advice && <div className="info-box">{insights.threshold_advice}</div>}
        <div className="buckets">
          <Group title="By fit score" group={insights.buckets.by_fit_score} />
          <Group title="By work mode" group={insights.buckets.by_work_mode} />
          <Group title="By experience asked" group={insights.buckets.by_experience_asked} />
        </div>
        <RankingBlock view={insights.ranking} api={api} onChange={r => setInsights({ ...insights, ranking: r })} onError={onError} />
        <p className="muted">
          {insights.ranking_test.enough_data
            ? `Ranking test on ${insights.ranking_test.decided} results: fit score alone ${insights.ranking_test.baseline_ap}, fit plus evidence score ${insights.ranking_test.candidate_ap}${insights.ranking_test.better ? ' (better)' : ' (not better)'}.`
            : `Ranking test needs ${insights.ranking_test.needed}; you have ${insights.ranking_test.decided} results. Nothing is learned from fewer.`}
        </p>
      </section>
    )}

    {/* Filter Navigation Bar */}
    <div className="tracker-filter-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '20px 0 12px' }}>
      <div className="pills">
        <button type="button" className={filterTab === 'active' ? 'active' : ''} onClick={() => setFilterTab('active')}>
          Active ({activeApps.length})
        </button>
        <button type="button" className={filterTab === 'archived' ? 'active' : ''} onClick={() => setFilterTab('archived')}>
          Archived ({archivedApps.length})
        </button>
        <button type="button" className={filterTab === 'all' ? 'active' : ''} onClick={() => setFilterTab('all')}>
          All ({apps.length})
        </button>
      </div>
      <small className="muted">{displayedApps.length} application{displayedApps.length === 1 ? '' : 's'} listed</small>
    </div>

    <section className="panel tracker-panel">
      {displayedApps.length === 0 && (
        <p className="muted" style={{ padding: '24px 16px', textAlign: 'center' }}>
          {filterTab === 'archived' ? 'No archived applications.' : 'No applications yet. Start the agent on the Live agent page.'}
        </p>
      )}
      {displayedApps.map(a => {
        const o = view(a);
        return (
          <article className={`tracker-row ${a.archived ? 'archived-row' : ''}`} key={a.id}>
            <div className="tracker-main">
              <b>{a.job.title}</b>
              <small>{a.job.company} · {a.job.match.score}% fit</small>
              <div className="tracker-chips">
                <Badge status={a.status} />
                <VerificationChip v={a.job.verification} />
                {a.archived && <span className="verify-chip" style={{ background: '#f1f5f9', color: '#64748b' }}>Archived</span>}
              </div>
            </div>

            {/* Preparation / Approval Controls */}
            {['prepared', 'approved'].includes(a.status) && (
              <button className="btn secondary" onClick={() => onReview(a.id)}>Review & approve</button>
            )}
            {a.status === 'approved' && (
              <button className="btn primary" onClick={() => onControl(a.id, 'start')}>Start application</button>
            )}

            {/* DEDICATED "Why it stopped?" Diagnostic Button */}
            {['stopped', 'failed', 'paused'].includes(a.status) && (
              <button
                className="btn warning-btn stop-info-btn"
                onClick={() => setSelectedDiag(a)}
                title="View detailed diagnostic explanation of why the agent stopped"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  background: '#fffbeb',
                  border: '1px solid #fcd34d',
                  color: '#92400e',
                  fontWeight: 600,
                  fontSize: '0.82rem',
                  padding: '7px 13px',
                  borderRadius: 8
                }}
              >
                <HelpCircle size={15} />
                <span>Why it stopped?</span>
              </button>
            )}

            {/* Retry Button */}
            {['stopped', 'failed'].includes(a.status) && (
              <button className="btn secondary" onClick={() => onControl(a.id, 'retry')}>
                <RotateCcw size={14} /> Retry application
              </button>
            )}

            {/* Running / Paused Outcome Controls */}
            {a.status === 'running' && (
              <div className="outcome-controls">
                <button className="btn secondary" onClick={() => onControl(a.id, 'pause')}>Pause</button>
                <button className="btn ghost" onClick={() => onControl(a.id, 'stop')}>Stop</button>
              </div>
            )}
            {['paused', 'needs_input'].includes(a.status) && (
              <div className="outcome-controls">
                <button className="btn primary" onClick={() => onControl(a.id, 'resume')}>Resume</button>
                <button className="btn ghost" onClick={() => onControl(a.id, 'stop')}>Stop</button>
              </div>
            )}
            {a.status === 'submitted' && (
              <div className="outcome-controls">
                <select aria-label="What happened" value={o.stage} onChange={e => change(a, { stage: e.target.value })}>
                  {Object.entries(STAGE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <button className={`icon-button ${o.fit_feedback === 'up' ? 'on' : ''}`} aria-label="Good fit" onClick={() => change(a, { fit_feedback: 'up' })}>
                  <ThumbsUp size={16} />
                </button>
                <button className={`icon-button ${o.fit_feedback === 'down' ? 'on' : ''}`} aria-label="Poor fit" onClick={() => change(a, { fit_feedback: 'down' })}>
                  <ThumbsDown size={16} />
                </button>
                <input
                  aria-label="Note"
                  placeholder="Note"
                  value={notes[a.id] ?? o.note}
                  onChange={e => setNotes({ ...notes, [a.id]: e.target.value })}
                  onBlur={() => { if (notes[a.id] !== undefined && notes[a.id] !== o.note) change(a, { note: notes[a.id] }); }}
                />
              </div>
            )}

            {(a.evidence?.confirmation_text || a.evidence?.screenshots?.confirmation) && (
              <a className="text-button" href={`/api/applications/${a.id}/evidence/confirmation`} target="_blank" rel="noreferrer">
                <ExternalLink size={14} />Evidence
              </a>
            )}

            {/* Archive & Delete Actions */}
            <div className="tracker-row-actions" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <button
                type="button"
                className={`icon-button ${a.archived ? 'on' : ''}`}
                title={a.archived ? 'Restore / Unarchive' : 'Archive application'}
                disabled={busyId === a.id}
                onClick={() => handleArchive(a.id)}
              >
                <Archive size={15} />
              </button>
              <button
                type="button"
                className="icon-button danger-hover"
                title="Delete application permanently"
                disabled={busyId === a.id}
                onClick={() => handleDelete(a.id, a.job.title)}
                style={{ color: '#ef4444' }}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </article>
        );
      })}
    </section>

    {/* DIAGNOSTIC REASON MODAL */}
    {selectedDiag && (
      <div className="modal-backdrop" onClick={() => setSelectedDiag(null)}>
        <section
          className="stop-reason-modal"
          role="dialog"
          aria-modal="true"
          aria-label="Agent Diagnostic Report"
          onClick={e => e.stopPropagation()}
          style={{
            background: '#fff',
            borderRadius: 16,
            maxWidth: 580,
            width: '90%',
            boxShadow: '0 20px 45px rgba(0,0,0,0.18)',
            padding: 24,
            margin: 'auto'
          }}
        >
          <div className="stop-modal-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18 }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <AlertTriangle size={22} color="#b45309" />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.2rem', color: '#111827' }}>Agent Status Diagnostic</h3>
                <p className="muted" style={{ margin: 0, fontSize: '0.84rem' }}>Clear explanation of why the agent stopped on this job</p>
              </div>
            </div>
            <button className="icon-button" aria-label="Close" onClick={() => setSelectedDiag(null)}>
              <X size={20} />
            </button>
          </div>

          <div className="stop-modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Job Header */}
            <div style={{ padding: '12px 16px', background: '#f8fafc', borderRadius: 10, border: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <b style={{ fontSize: '1rem', color: '#0f172a' }}>{selectedDiag.job.title}</b>
                <div style={{ fontSize: '0.82rem', color: '#64748b', marginTop: 2 }}>
                  {selectedDiag.job.company} · {selectedDiag.job.source || 'Job Board'} · {selectedDiag.job.match?.score || 0}% fit
                </div>
              </div>
              <Badge status={selectedDiag.status} />
            </div>

            {/* Diagnostic Reason Box */}
            <div style={{ padding: 16, background: '#fffbeb', borderRadius: 12, border: '1px solid #fde68a' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '3px 8px', borderRadius: 999, background: '#fef3c7', color: '#92400e', textTransform: 'uppercase' }}>
                  {selectedDiag.diagnostic?.category?.replace('_', ' ') || 'STOPPED / PAUSED'}
                </span>
                <h4 style={{ margin: 0, fontSize: '1rem', color: '#92400e', fontWeight: 700 }}>
                  {selectedDiag.diagnostic?.headline || 'Agent Paused on this Opening'}
                </h4>
              </div>
              <p style={{ margin: 0, fontSize: '0.9rem', color: '#78350f', lineHeight: 1.5 }}>
                {selectedDiag.diagnostic?.explanation ||
                  selectedDiag.events?.slice().reverse().find(e => e.text.toLowerCase().includes('skipped') || e.text.toLowerCase().includes('stopped'))?.text ||
                  'The agent stopped during processing because this application requires candidate intervention or the job portal closed the opening.'}
              </p>
              {selectedDiag.diagnostic?.recommendation && (
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px dashed #fcd34d', fontSize: '0.85rem', color: '#92400e' }}>
                  <b>What you should do:</b> {selectedDiag.diagnostic.recommendation}
                </div>
              )}
            </div>

            {/* Latest Raw Trace */}
            {selectedDiag.events && selectedDiag.events.length > 0 && (
              <div style={{ padding: '10px 14px', background: '#f1f5f9', borderRadius: 8, fontSize: '0.8rem' }}>
                <b style={{ display: 'block', color: '#475569', marginBottom: 4 }}>Last Agent Log:</b>
                <code style={{ color: '#1e293b', wordBreak: 'break-word', display: 'block' }}>
                  {selectedDiag.events[selectedDiag.events.length - 1].text}
                </code>
                <small style={{ color: '#94a3b8', display: 'block', marginTop: 4 }}>
                  {new Date(selectedDiag.events[selectedDiag.events.length - 1].time).toLocaleString()}
                </small>
              </div>
            )}
          </div>

          {/* Modal Footer Controls */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'flex-end', marginTop: 22, paddingTop: 16, borderTop: '1px solid #e2e8f0' }}>
            {selectedDiag.job.url && (
              <a className="btn secondary" href={selectedDiag.job.url} target="_blank" rel="noreferrer" style={{ fontSize: '0.85rem' }}>
                <ExternalLink size={15} /> Open original listing
              </a>
            )}
            {['stopped', 'failed'].includes(selectedDiag.status) && (
              <button
                className="btn primary"
                onClick={() => {
                  onControl(selectedDiag.id, 'retry');
                  setSelectedDiag(null);
                }}
                style={{ fontSize: '0.85rem' }}
              >
                <RotateCcw size={15} /> Retry application
              </button>
            )}
            <button
              className="btn secondary"
              onClick={() => {
                handleArchive(selectedDiag.id);
                setSelectedDiag(null);
              }}
              style={{ fontSize: '0.85rem' }}
            >
              <Archive size={15} /> {selectedDiag.archived ? 'Unarchive' : 'Archive'}
            </button>
            <button
              className="btn ghost danger"
              onClick={() => {
                handleDelete(selectedDiag.id, selectedDiag.job.title);
                setSelectedDiag(null);
              }}
              style={{ fontSize: '0.85rem', color: '#ef4444' }}
            >
              <Trash2 size={15} /> Delete application
            </button>
          </div>
        </section>
      </div>
    )}
  </>;
}

export type Telemetry = {
  portal?: string;
  execution_mode?: string;
  current_url?: string;
  target_domain?: string;
  connection_state?: string;
  session_state?: string;
  last_navigation?: string;
  active_job?: {
    title?: string;
    company?: string;
    location?: string;
    score?: number;
    stage?: string;
  };
  auth_info?: {
    required?: boolean;
    checkpoint_type?: string | null;
    prompt?: string;
  };
  app_info?: {
    stage?: string;
    missing_fields?: string[];
    resume_uploaded?: boolean;
    ready_for_review?: boolean;
    awaiting_approval?: boolean;
    submission_result?: string | null;
  };
};

export type Checkpoint = {
  type: string;
  prompt: string;
  field?: string;
  sensitive?: boolean;
  job_id?: string;
  current_url?: string;
  created_at?: string;
};

export function LiveBrowserTelemetryPanel({
  telemetry,
  checkpoint,
  agentStatus,
  portalName,
  onCheckpointSubmit,
  onResume,
  onRetry,
  onStart,
}: {
  telemetry?: Telemetry | null;
  checkpoint?: Checkpoint | null;
  agentStatus: string;
  portalName?: string;
  onCheckpointSubmit?: (checkpointType: string, value: string) => Promise<void>;
  onResume?: () => void;
  onRetry?: () => void;
  onStart?: () => void;
}) {
  const [inputValue, setInputValue] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const t = telemetry || {};
  const portal = t.portal || portalName || 'Indeed';
  const execMode = t.execution_mode || 'Visible Chrome';
  const currentUrl = t.current_url || '';
  const domain = t.target_domain || (portal === 'Indeed' ? 'indeed.com' : portal === 'Naukri' ? 'naukri.com' : portal === 'Internshala' ? 'internshala.com' : 'linkedin.com');
  const connState = t.connection_state || (['running', 'searching', 'needs_input'].includes(agentStatus) ? 'connected' : 'idle');
  const sessionState = t.session_state || agentStatus;
  const activeJob = t.active_job || {};
  const authInfo = t.auth_info || {};
  const appInfo = t.app_info || {};

  const isAuthCheckpoint = !!checkpoint || !!authInfo.required;
  const chkType = checkpoint?.type || authInfo.checkpoint_type || 'auth';
  const promptText = checkpoint?.prompt || authInfo.prompt || 'Authentication input required to continue.';

  const isFailed = agentStatus === 'failed' || sessionState === 'failed';
  const isAwaitingInput = agentStatus === 'needs_input' || isAuthCheckpoint;

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || !onCheckpointSubmit) return;
    setSubmitting(true);
    try {
      await onCheckpointSubmit(chkType, inputValue.trim());
      setInputValue('');
    } finally {
      setSubmitting(false);
    }
  };

  const openPortalTab = () => {
    const url = currentUrl && currentUrl.startsWith('http') ? currentUrl : portal === 'Indeed' ? 'https://www.indeed.com' : portal === 'Naukri' ? 'https://www.naukri.com' : portal === 'Internshala' ? 'https://internshala.com' : 'https://www.linkedin.com';
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <section className="panel modern-plan-panel" style={{ marginTop: 20, border: '1px solid #c9d7fc', background: '#f8faff' }}>
      <div className="panel-heading" style={{ borderBottom: '1px solid #e1eafc', paddingBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ padding: '6px 10px', borderRadius: 8, background: portal === 'Indeed' ? '#2164f3' : portal === 'Naukri' ? '#ff7555' : portal === 'Internshala' ? '#00a5ec' : '#0a66c2', color: '#fff', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '0.85rem' }}>
            <Radio size={14}/>
            <span>{portal} Real-Time Portal & Browser</span>
          </div>
          <span style={{ fontSize: '0.78rem', background: '#e8f0fe', color: '#1a73e8', padding: '3px 8px', borderRadius: 6, fontWeight: 600 }}>
            {execMode}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: '0.78rem', color: connState === 'connected' ? '#0d8a43' : connState === 'connecting' ? '#e67e22' : '#d93025', fontWeight: 600 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: connState === 'connected' ? '#0d8a43' : connState === 'connecting' ? '#e67e22' : '#d93025' }}/>
            {connState}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn secondary" style={{ fontSize: '0.78rem', padding: '5px 11px' }} onClick={openPortalTab}>
            <ExternalLink size={13}/>
            <span>Open Portal Tab</span>
          </button>
          {['stopped', 'idle', 'completed'].includes(agentStatus) && onStart && (
            <button type="button" className="btn primary" style={{ fontSize: '0.78rem', padding: '5px 11px' }} onClick={onStart}>
              <Play size={13}/>
              <span>Start {portal} Agent</span>
            </button>
          )}
          {isAwaitingInput && onResume && (
            <button type="button" className="btn primary" style={{ fontSize: '0.78rem', padding: '5px 11px' }} onClick={onResume}>
              <Play size={13}/>
              <span>Resume Agent</span>
            </button>
          )}
          {isFailed && onRetry && (
            <button type="button" className="btn secondary" style={{ fontSize: '0.78rem', padding: '5px 11px' }} onClick={onRetry}>
              <RefreshCw size={13}/>
              <span>Retry Agent</span>
            </button>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginTop: 14 }}>
        <div style={{ background: '#fff', padding: '12px 14px', borderRadius: 10, border: '1px solid #e1eafc' }}>
          <small style={{ color: '#666', textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: 700 }}>Target Domain & URL</small>
          <div style={{ fontWeight: 600, fontSize: '0.86rem', marginTop: 4, wordBreak: 'break-all' }}>{domain}</div>
          <small style={{ color: '#888', fontSize: '0.74rem', display: 'block', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={currentUrl}>
            {currentUrl || 'No active navigation yet'}
          </small>
        </div>

        <div style={{ background: '#fff', padding: '12px 14px', borderRadius: 10, border: '1px solid #e1eafc' }}>
          <small style={{ color: '#666', textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: 700 }}>Session State Machine</small>
          <div style={{ fontWeight: 700, fontSize: '0.92rem', marginTop: 4, color: isAwaitingInput ? '#d97706' : isFailed ? '#dc2626' : ['stopped', 'idle'].includes(sessionState) ? '#64748b' : '#2563eb' }}>
            {['stopped', 'idle'].includes(sessionState) ? 'Ready (Idle)' : sessionState.replace(/_/g, ' ')}
          </div>
          <small style={{ color: '#888', fontSize: '0.74rem', display: 'block', marginTop: 2 }}>
            {['stopped', 'idle'].includes(sessionState) ? 'Agent is waiting. Click Start Agent to run.' : t.last_navigation ? `Navigated ${new Date(t.last_navigation).toLocaleTimeString()}` : 'Ready for instruction'}
          </small>
        </div>

        <div style={{ background: '#fff', padding: '12px 14px', borderRadius: 10, border: '1px solid #e1eafc' }}>
          <small style={{ color: '#666', textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: 700 }}>Application Lifecycle</small>
          <div style={{ fontWeight: 600, fontSize: '0.86rem', marginTop: 4 }}>
            Stage: {appInfo.stage || 'discovery'}
          </div>
          <small style={{ color: '#888', fontSize: '0.74rem', display: 'block', marginTop: 2 }}>
            {appInfo.resume_uploaded ? 'Resume uploaded · ' : ''}
            {appInfo.awaiting_approval ? 'Awaiting user approval' : appInfo.ready_for_review ? 'Ready for review' : 'Active search / inspection'}
          </small>
        </div>
      </div>

      {activeJob.title && (
        <div style={{ marginTop: 14, background: '#fff', padding: '12px 16px', borderRadius: 10, border: '1px solid #d4e2fd', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 34, height: 34, borderRadius: 8, background: '#edf2fe', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#2164f3' }}>
              <Briefcase size={18}/>
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.92rem', color: '#111' }}>{activeJob.title}</div>
              <small style={{ color: '#666' }}>{activeJob.company} {activeJob.location ? `· ${activeJob.location}` : ''}</small>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {activeJob.score !== undefined && activeJob.score > 0 && (
              <span style={{ background: '#eafbf0', color: '#0d8a43', padding: '4px 10px', borderRadius: 12, fontWeight: 700, fontSize: '0.82rem' }}>
                {activeJob.score}% match
              </span>
            )}
            <span style={{ fontSize: '0.8rem', background: '#f1f3f9', color: '#444', padding: '4px 9px', borderRadius: 6, fontWeight: 600 }}>
              {activeJob.stage || 'inspecting'}
            </span>
          </div>
        </div>
      )}

      {isAuthCheckpoint && (
        <div style={{ marginTop: 14, background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#b45309', fontWeight: 700, fontSize: '0.88rem' }}>
            <KeyRound size={16}/>
            <span>Checkpoint Required: {chkType.replace(/_/g, ' ')}</span>
          </div>
          <p style={{ margin: '6px 0 12px 0', fontSize: '0.84rem', color: '#78350f' }}>{promptText}</p>
          
          {chkType !== 'challenge' && chkType !== 'user_verification' ? (
            <form onSubmit={handleFormSubmit} style={{ display: 'flex', gap: 8, maxWidth: 440 }}>
              <input
                type={chkType === 'password' ? 'password' : chkType === 'otp' || chkType === 'phone' ? 'tel' : 'text'}
                placeholder={chkType === 'email' ? 'Enter your email' : chkType === 'password' ? 'Enter your password' : chkType === 'otp' ? 'Enter verification code' : chkType === 'phone' ? 'Enter phone number' : 'Enter answer'}
                value={inputValue}
                onChange={e => setInputValue(e.target.value)}
                style={{ flex: 1, padding: '7px 12px', borderRadius: 8, border: '1px solid #d97706', fontSize: '0.86rem', outline: 'none' }}
                disabled={submitting}
                autoFocus
              />
              <button type="submit" className="btn primary" disabled={submitting || !inputValue.trim()} style={{ fontSize: '0.82rem', padding: '6px 14px' }}>
                <Send size={13}/>
                <span>{submitting ? 'Submitting…' : 'Submit to Agent'}</span>
              </button>
            </form>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button type="button" className="btn secondary" onClick={openPortalTab}>
                <ExternalLink size={14}/>
                <span>Solve in Browser Tab</span>
              </button>
              {onResume && (
                <button type="button" className="btn primary" onClick={onResume}>
                  <Play size={14}/>
                  <span>I Completed It — Resume Agent</span>
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function AutoLoginVaultCard({
  activePlatform,
  onPlatformChange,
  onConnect,
  isAgentRunning,
}: {
  activePlatform: string;
  onPlatformChange?: (platform: string) => void;
  onConnect?: (platform: string) => Promise<void>;
  isAgentRunning?: boolean;
}) {
  const [platform, setPlatform] = useState(activePlatform || 'Internshala');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [hasSaved, setHasSaved] = useState(false);
  const [savedEmail, setSavedEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (activePlatform && activePlatform !== platform) {
      setPlatform(activePlatform);
    }
  }, [activePlatform]);

  useEffect(() => {
    let active = true;
    const fetchStatus = async () => {
      try {
        const res = await fetch(`/api/connections/${platform.toLowerCase()}/credentials`, { credentials: 'include' });
        if (!res.ok) return;
        const data = await res.json();
        if (active) {
          setHasSaved(!!data.has_credentials);
          setSavedEmail(data.email || '');
          if (data.email && !email) {
            setEmail(data.email);
          }
        }
      } catch {}
    };
    fetchStatus();
    return () => { active = false; };
  }, [platform]);

  const handlePlatformSelect = (p: string) => {
    setPlatform(p);
    setNotice(null);
    onPlatformChange?.(p);
  };

  const handleSave = async (autoLaunch: boolean = false) => {
    const finalEmail = (email.trim() || savedEmail).trim();
    const finalPassword = password.trim();

    if (!finalEmail || (!hasSaved && !finalPassword)) {
      setNotice('Please provide both email/username and password.');
      return;
    }
    setLoading(true);
    setNotice(null);
    try {
      if (autoLaunch) {
        setNotice(`Launching Chrome desktop browser and auto-logging into ${platform}...`);
        const res = await fetch(`/api/connections/${platform.toLowerCase()}/auto-login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ email: finalEmail, password: finalPassword || undefined }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Auto-login request failed.');
        }
        const data = await res.json();
        setHasSaved(true);
        setSavedEmail(finalEmail);
        setNotice(data.message || `Auto-login completed for ${platform}!`);
        if (onConnect) {
          await onConnect(platform);
        }
      } else {
        if (!finalPassword) {
          setNotice('Enter a new password to update stored credentials.');
          setLoading(false);
          return;
        }
        const res = await fetch(`/api/connections/${platform.toLowerCase()}/credentials`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ email: finalEmail, password: finalPassword }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Failed to save credentials.');
        }
        setHasSaved(true);
        setSavedEmail(finalEmail);
        setNotice(`Credentials saved locally for ${platform}. Agent will auto-fill on next run.`);
      }
    } catch (e: any) {
      setNotice(e?.message || 'Error saving credentials.');
    } finally {
      setLoading(false);
    }
  };

  const platformColor =
    platform === 'Indeed' ? '#2164f3' :
    platform === 'Naukri' ? '#ff7555' :
    platform === 'Internshala' ? '#00a5ec' : '#0a66c2';

  return (
    <section className="panel modern-plan-panel" style={{ marginTop: 16, border: '1px solid #d0d7de', background: '#ffffff', borderRadius: 12, padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, borderBottom: '1px solid #eaeef2', paddingBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#1f2937' }}>
            <KeyRound size={20} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '0.96rem', fontWeight: 700, color: '#111827', display: 'flex', alignItems: 'center', gap: 8 }}>
              Universal Auto-Login Vault
              <span style={{ fontSize: '0.72rem', fontWeight: 600, padding: '2px 8px', borderRadius: 999, background: hasSaved ? '#dcfce7' : '#f3f4f6', color: hasSaved ? '#15803d' : '#6b7280' }}>
                {hasSaved ? 'Configured locally (SQLite)' : 'Not configured yet'}
              </span>
            </h3>
            <p style={{ margin: '2px 0 0', fontSize: '0.78rem', color: '#6b7280' }}>
              Local browser agent auto-fills your login form with human-like keystroke delays (30ms).
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#4b5563' }}>Platform:</span>
          <select
            value={platform}
            onChange={e => handlePlatformSelect(e.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: 8,
              border: '1px solid #cbd5e1',
              background: '#fff',
              fontSize: '0.84rem',
              fontWeight: 600,
              color: '#1e293b',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value="Internshala">Internshala</option>
            <option value="Naukri">Naukri</option>
            <option value="LinkedIn">LinkedIn</option>
            <option value="Indeed">Indeed</option>
          </select>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: platformColor }} title={platform}/>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginTop: 16 }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.76rem', fontWeight: 700, color: '#374151', textTransform: 'uppercase', marginBottom: 6 }}>
            {platform} Email / Username
          </label>
          <input
            type="text"
            placeholder={savedEmail || `Enter your ${platform} email`}
            value={email}
            onChange={e => setEmail(e.target.value)}
            disabled={loading}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: 8,
              border: '1px solid #d1d5db',
              fontSize: '0.86rem',
              outline: 'none',
              boxSizing: 'border-box'
            }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: '0.76rem', fontWeight: 700, color: '#374151', textTransform: 'uppercase', marginBottom: 6 }}>
            {platform} Password
          </label>
          <div style={{ position: 'relative' }}>
            <input
              type={showPassword ? 'text' : 'password'}
              placeholder={hasSaved ? '•••••••••••• (Leave blank to keep saved)' : `Enter your ${platform} password`}
              value={password}
              onChange={e => setPassword(e.target.value)}
              disabled={loading}
              style={{
                width: '100%',
                padding: '8px 36px 8px 12px',
                borderRadius: 8,
                border: '1px solid #d1d5db',
                fontSize: '0.86rem',
                outline: 'none',
                boxSizing: 'border-box'
              }}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              style={{
                position: 'absolute',
                right: 8,
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: '#6b7280',
                padding: 4,
                display: 'flex',
                alignItems: 'center'
              }}
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>
      </div>

      {notice && (
        <div style={{ marginTop: 12, padding: '8px 12px', borderRadius: 8, background: '#f0fdf4', border: '1px solid #bbf7d0', fontSize: '0.8rem', color: '#166534', display: 'flex', alignItems: 'center', gap: 6 }}>
          <CheckCircle2 size={15} />
          <span>{notice}</span>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 16, paddingTop: 12, borderTop: '1px solid #f3f4f6', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.76rem', color: '#6b7280' }}>
          <Lock size={13} />
          <span>Stored in SQLite on your device only. Never transmitted to third-party APIs.</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            type="button"
            className="btn secondary"
            disabled={loading || (!email.trim() && !savedEmail) || !password.trim()}
            onClick={() => handleSave(false)}
            style={{ fontSize: '0.8rem', padding: '6px 14px' }}
          >
            Save Credentials
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={loading || (!hasSaved && (!email.trim() || !password.trim())) || (hasSaved && !email.trim() && !savedEmail)}
            onClick={() => handleSave(true)}
            style={{ fontSize: '0.8rem', padding: '6px 16px', background: platformColor, borderColor: platformColor }}
          >
            <Play size={14} />
            <span>{loading ? 'Connecting…' : `Save & Auto-Login ${platform}`}</span>
          </button>
        </div>
      </div>
    </section>
  );
}

export function ConnectingProgressCard({
  platform,
  onCancel,
  estimatedSeconds = 15,
}: {
  platform: 'LinkedIn' | 'Indeed' | 'Naukri' | 'Internshala';
  onCancel?: () => void;
  estimatedSeconds?: number;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setElapsed(0);
    const timer = setInterval(() => {
      setElapsed(prev => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [platform]);

  const remaining = Math.max(1, estimatedSeconds - elapsed);
  const progressPercent = Math.min(95, Math.round((Math.min(elapsed, estimatedSeconds) / estimatedSeconds) * 100));

  const platformColor =
    platform === 'Indeed' ? '#2164f3' :
    platform === 'Naukri' ? '#ff7555' :
    platform === 'Internshala' ? '#00a5ec' : '#0a66c2';

  const stageText =
    elapsed < 3
      ? `Launching secure desktop Chrome session for ${platform}...`
      : elapsed < 7
      ? `Navigating to ${platform} authentication gateway...`
      : elapsed < 12
      ? `Auto-filling credentials & validating session...`
      : `Synchronizing account connection state...`;

  return (
    <div
      className="panel modern-connecting-card"
      style={{
        margin: '18px 0',
        padding: '30px 24px',
        background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
        border: '1px solid #e2e8f0',
        borderRadius: 14,
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.04)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        position: 'relative',
        overflow: 'hidden'
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: `linear-gradient(90deg, ${platformColor}, #818cf8)`
        }}
      />

      <div style={{ position: 'relative', width: 68, height: 68, marginBottom: 14 }}>
        <div
          className="pulse-glow"
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            background: platformColor,
            opacity: 0.18
          }}
        />
        <div
          style={{
            width: '100%',
            height: '100%',
            borderRadius: '50%',
            background: '#ffffff',
            border: '2px solid #eef2f6',
            boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        >
          <RefreshCw className="spin" size={30} color={platformColor} />
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span
          style={{
            fontSize: '0.72rem',
            fontWeight: 700,
            padding: '2px 8px',
            borderRadius: 999,
            background: `${platformColor}18`,
            color: platformColor,
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}
        >
          {platform}
        </span>
        <h3 style={{ margin: 0, fontSize: '1.18rem', fontWeight: 750, color: '#0f172a' }}>
          Connecting to {platform}...
        </h3>
      </div>

      <p style={{ margin: '0 0 16px', fontSize: '0.84rem', color: '#64748b', maxWidth: 440 }}>
        {stageText}
      </p>

      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 14px',
          borderRadius: 999,
          background: '#f1f5f9',
          border: '1px solid #e2e8f0',
          fontSize: '0.8rem',
          fontWeight: 650,
          color: '#334155',
          marginBottom: 16
        }}
      >
        <Clock size={14} color={platformColor} />
        <span>Estimated time: ~{remaining}s remaining</span>
        <span style={{ color: '#94a3b8' }}>•</span>
        <span style={{ color: platformColor }}>{progressPercent}%</span>
      </div>

      <div
        style={{
          width: '100%',
          maxWidth: 380,
          height: 8,
          background: '#e2e8f0',
          borderRadius: 999,
          overflow: 'hidden',
          marginBottom: 20
        }}
      >
        <div
          style={{
            width: `${progressPercent}%`,
            height: '100%',
            background: `linear-gradient(90deg, ${platformColor}, #818cf8)`,
            borderRadius: 999,
            transition: 'width 0.4s ease'
          }}
        />
      </div>

      {onCancel && (
        <button
          type="button"
          className="btn ghost"
          onClick={onCancel}
          style={{
            fontSize: '0.82rem',
            padding: '6px 16px',
            color: '#64748b',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            borderRadius: 8
          }}
        >
          <X size={15} />
          <span>Cancel Connection</span>
        </button>
      )}
    </div>
  );
}


