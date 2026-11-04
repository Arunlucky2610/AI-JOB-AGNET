'use client';
import { useEffect, useState, useCallback } from 'react';
import { ArrowUpRight, ArrowRight, ArrowLeft, LayoutDashboard, Search, BriefcaseBusiness, Radio, SlidersHorizontal, UserRound, Sparkles, ChevronDown, Check, CheckCheck, X, MapPin, Clock3, Globe2, Upload, FileText, Play, Pause, Square, MousePointer2, Download, ExternalLink, LogOut, CircleHelp, Orbit, LoaderCircle, CheckCircle2, AlertCircle, Menu, Plus, Settings2, Layers3, ShieldCheck, RefreshCw, Eye, Maximize2, Minimize2, PanelLeftClose, PanelLeftOpen, Archive, Trash2, AlertTriangle } from 'lucide-react';

import Onboarding, {type Candidate} from './onboarding';
import {PlanPanel,ShortlistPanel,TracePanel,ClaimsPanel,EvidenceBlock,TrackerView,VerificationChip,AutoLoginVaultCard,ConnectingProgressCard,type Plan,type ShortItem,type TraceItem,type Outcome,type Grounding,type Evidence,type Verification,type Telemetry,type Checkpoint} from './agent-panels';

/** The cloud browser, large by default, with a full-screen mode (Esc exits) and an open-in-new-tab link. */
function LiveFrame({src,title,interactive}:{src:string;title:string;interactive:boolean}) {
  const [full,setFull]=useState(false);
  useEffect(()=>{
    if(!full)return;
    const onKey=(e:KeyboardEvent)=>{if(e.key==='Escape')setFull(false)};
    window.addEventListener('keydown',onKey);
    return()=>window.removeEventListener('keydown',onKey);
  },[full]);
  return <div className={`live-shell ${full?'full':''}`}>
    <div className="live-tools">
      <span>{interactive?'Your turn: click inside the browser to type':'The agent is driving; you are watching'}</span>
      <a className="text-button" href={src} target="_blank" rel="noopener noreferrer"><ExternalLink size={14}/>New tab</a>
      <button type="button" className="text-button" onClick={()=>setFull(!full)}>{full?<Minimize2 size={14}/>:<Maximize2 size={14}/>}{full?'Exit full screen (Esc)':'Full screen'}</button>
    </div>
    <iframe title={title} src={src} className={`live-frame ${interactive?'interactive':''}`} sandbox="allow-same-origin allow-scripts allow-forms" allow="clipboard-read; clipboard-write"/>
  </div>;
}
type Profile = Candidate;
type Settings = {source_focus?:'linkedin'|'indeed'|'naukri'|'internshala';matching?:'strict'|'fresher_ai';mode:string;daily_limit:number;threshold:number|null;effective_threshold?:number;auto_enabled:boolean};
type User = {name:string;email:string;demo:boolean;profile:Profile;settings:Settings};
type Match = {score:number;matched:boolean;eligible:boolean;matched_skills:string[];missing_skills:string[];blockers:string[];unknown:string[];method:string;explanation?:string;match_score?:number;matching_skills?:string[];missing_required_skills?:string[];missing_preferred_skills?:string[];experience_alignment?:string;location_alignment?:string;salary_alignment?:string;eligibility_concerns?:string[];recommendation?:string;evaluation?:{A:string;B:{requirement:string;importance:string;tier:string;jd_evidence:string;profile_evidence:string;match:string}[];C:string;D:string;E:string;F:string;G:string;H:string;global_score:number};review_notes?:string[]};
type Job = {id:string;title:string;company:string;location:string;country:string;mode:string;source:string;skills:string[];salary:string;color:string;description:string;url:string;application_url?:string;status?:string;verified_at?:string;posted?:string;source_attribution?:string;demo:boolean;discovery_url?:string;verification?:Verification;match:Match;archived?:boolean};
type Pack = {resume:string;cover_letter:string;recruiter_message?:string;notes:string[];answers:Record<string,string>;confirmed_claims?:string[];diff?:string};
type Application = {id:string;job:Job;status:string;package:Pack;events:{time:string;text:string}[];live_url?:string;created:string;updated:string;approved:boolean;step:number;human_reason?:string;outcome:Outcome|null;grounding?:Grounding;evidence?:Evidence|null;archived?:boolean;diagnostic?:any};
type Analytics = {discovered:number;evaluated:number;matched:number;packages:number;counts:Record<string,number>;trend:{day:string;discovered:number;submitted:number}[];sources:Record<string,number>};
type Integration = {openrouter:boolean;openrouter_status?:string;browserbase:boolean;browserbase_status?:string;use_local_browser?:boolean;model:string;sources:{name:string;enabled:boolean;connected:boolean}[]};
type AgentState={id:string|null;login_wait?:boolean;status:string;phase:string;events:{time:string;text:string}[];live_url?:string;searched?:number;inspected?:number;candidate_pages?:number;human_reason?:string;needed?:{question:string;job:string}[];prefiltered?:number;spend?:{usd:number;calls:number;cap:number};plan?:Plan|null;ranking_version?:string|null;shortlist?:ShortItem[];trace?:TraceItem[];telemetry?:Telemetry;checkpoint?:Checkpoint};

type DiscoveryProgress = {
  queries_executed?: number;
  sources_searched?: number;
  pages_inspected?: number;
  listings_discovered?: number;
  valid_listings?: number;
  duplicates_removed?: number;
  jobs_matching?: number;
  jobs_saved?: number;
  failed_sources?: number;
};
type DiscoveryRunState = {
  id?: string;
  status: 'idle' | 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled';
  phase: string;
  progress: DiscoveryProgress;
  search_config?: any;
  events: { time: string; text: string }[];
  results_count: number;
  error?: string | null;
  completed_at?: string | null;
};

const tabs = [{name:'Overview',icon:LayoutDashboard},{name:'Live agent',icon:Radio},{name:'Find Jobs',icon:Search},{name:'Applications',icon:BriefcaseBusiness},{name:'My profile',icon:UserRound},{name:'Preferences',icon:SlidersHorizontal}];
const labels:Record<string,string>={prepared:'Ready for review',approved:'Approved',running:'Applying',submitted:'Applied',paused:'Paused',needs_input:'Needs your input',stopped:'Stopped',failed:'Failed',needs_verification:'Verify submission',submitting:'Submitting'};
async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{const r=await fetch(`/api${path}`,{method,signal:AbortSignal.timeout(110000),credentials:'include',headers:body instanceof FormData?{}:{'Content-Type':'application/json'},...(body===undefined?{}:{body:body instanceof FormData?body:JSON.stringify(body)})});if(!r.ok){const d=await r.json().catch(()=>({detail:'The server could not be reached.'}));const msg=typeof d.detail==='string'?d.detail:Array.isArray(d.detail)&&d.detail[0]?.msg?d.detail[0].msg:'An error occurred. Please try again.';throw Error(msg);}return r.json();}
function Badge({status}:{status:string}){return <span className={`badge ${status}`}><span/>{labels[status]||status}</span>}
function Logo({job,large=false}:{job:Job;large?:boolean}){return <div className={`company-logo ${large?'large':''}`} style={{background:job.color||'#c2f970'}}>{job.company.slice(0,1).toUpperCase()}</div>}
function Empty({title,body,action}:{title:string;body:string;action?:React.ReactNode}){return <div className="empty"><Orbit size={36}/><h3>{title}</h3><p>{body}</p>{action}</div>}

export default function Home(){
 const [editingProfile,setEditingProfile]=useState(false);
 const [connectionLost,setConnectionLost]=useState(false);
 const [humanNoticeSeen,setHumanNoticeSeen]=useState('');
 const [agent,setAgent]=useState<AgentState>({id:null,status:'idle',phase:'ready',events:[]});
 const [discoveryRun,setDiscoveryRun]=useState<DiscoveryRunState|null>(null);
 const [minScoreFilter,setMinScoreFilter]=useState<number>(0);
 const [sourceFilter,setSourceFilter]=useState<string>('All');
 const [modeFilter,setModeFilter]=useState<string>('All');
 const [eligibilityFilter,setEligibilityFilter]=useState<string>('All');
 const [sortBy,setSortBy]=useState<string>('score_desc');
 const [user,setUser]=useState<User|null>(null),[boot,setBoot]=useState(true),[tab,setTab]=useState('Overview'),[jobs,setJobs]=useState<Job[]>([]),[apps,setApps]=useState<Application[]>([]),[stats,setStats]=useState<Analytics|null>(null),[integration,setIntegration]=useState<Integration|null>(null),[days,setDays]=useState(7),[busy,setBusy]=useState(''),[notice,setNotice]=useState(''),[error,setError]=useState(''),[query,setQuery]=useState(''),[filter,setFilter]=useState('All jobs'),[selected,setSelected]=useState<Job|null>(null),[review,setReview]=useState<Application|null>(null),[pack,setPack]=useState<Pack|null>(null),[docTab,setDocTab]=useState<'resume'|'cover_letter'|'recruiter_message'>('resume'),[editDocument,setEditDocument]=useState(false),[liveId,setLiveId]=useState(''),[searchOpen,setSearchOpen]=useState(false),[mobile,setMobile]=useState(false),[sidebarCollapsed,setSidebarCollapsed]=useState(false),[profile,setProfile]=useState<Profile|null>(null),[settings,setSettings]=useState<Settings|null>(null),[profileStep,setProfileStep]=useState(0),[workspaceReady]=useState(true);
 const [customQuery,setCustomQuery]=useState(''),[customLoc,setCustomLoc]=useState(''),[customRemote,setCustomRemote]=useState(false),[discoverBusy,setDiscoverBusy]=useState(false);
 const [testOrBusy,setTestOrBusy]=useState(false),[testBbBusy,setTestBbBusy]=useState(false),[orStatusText,setOrStatusText]=useState(''),[bbStatusText,setBbStatusText]=useState('');
 const [orKeyInput,setOrKeyInput]=useState(''),[bbKeyInput,setBbKeyInput]=useState(''),[showKeyConfig,setShowKeyConfig]=useState(false),[showDiff,setShowDiff]=useState(false);
 const refresh=useCallback(async()=>{const [j,a,s,i,r]=await Promise.all([api<Job[]>('/jobs'),api<Application[]>('/applications'),api<Analytics>(`/analytics?days=${days}`),api<Integration>('/integrations'),api<AgentState>('/agent')]);setConnectionLost(false);setAgent(r);setJobs(j);setApps(a);setStats(s);setIntegration(i);},[days]);
 const pollDiscovery=useCallback(async()=>{
  try{
   const st=await api<DiscoveryRunState>('/jobs/discover/status');
   if(st&&st.status){
    setDiscoveryRun(prev=>{
     if(prev?.status==='running'&&(st.status==='completed'||st.status==='completed_with_warnings')){
      refresh().catch(()=>{});
      setNotice(`Discovery finished! ${st.results_count||0} matching vacancies found.`);
     }
     return st;
    });
   }
  }catch{}
 },[refresh]);
 useEffect(()=>{if(!user)return;pollDiscovery();const t=setInterval(pollDiscovery,discoveryRun?.status==='running'?1500:8000);return()=>clearInterval(t);},[user,discoveryRun?.status,pollDiscovery]);
 useEffect(()=>{api<User>('/workspace/init','POST',{}).then(u=>{setUser(u);setProfile(u.profile);setSettings(u.settings)}).catch(e=>setError(e.message)).finally(()=>setBoot(false));},[]);
 useEffect(()=>{if(!user)return;refresh().catch(e=>setError(e.message));const events=new EventSource('/api/events');events.addEventListener('refresh',()=>refresh().catch(()=>setConnectionLost(true)));const poll=setInterval(()=>refresh().catch(()=>setConnectionLost(true)),3000);return()=>{events.close();clearInterval(poll)};},[user,refresh]);
 useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),5000);return()=>clearTimeout(t)},[notice]);
 useEffect(()=>{if(!user?.demo)return;const running=apps.find(a=>a.status==='running');if(!running)return;const timer=setTimeout(()=>api(`/applications/${running.id}/action`,'POST',{action:'demo_advance'}).then(refresh).catch(()=>{}),2400);return()=>clearTimeout(timer);},[apps,user?.demo,refresh]);
 useEffect(()=>{if(!selected&&!review&&!searchOpen)return;const previous=document.activeElement as HTMLElement|null;const dialog=document.querySelector('[role="dialog"]') as HTMLElement|null;if(!dialog)return;const focusables=()=>Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input,select,textarea,[tabindex="0"]'));focusables()[0]?.focus();const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){setSelected(null);setReview(null);setSearchOpen(false)}if(e.key==='Tab'){const list=focusables();const first=list[0],last=list[list.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}};document.addEventListener('keydown',key);const overflow=document.body.style.overflow;document.body.style.overflow='hidden';return()=>{document.removeEventListener('keydown',key);document.body.style.overflow=overflow;previous?.focus()};},[!!selected,!!review,searchOpen]);
 const act=async(key:string,fn:()=>Promise<void>)=>{if(busy)return;setBusy(key);setError('');try{await fn()}catch(e){setError(e instanceof DOMException&&e.name==='TimeoutError'?'This request took too long. Please retry; no application was submitted.':e instanceof Error?e.message:'Something went wrong.')}finally{setBusy('')}};
 const switchWorkspace=()=>act('workspace',async()=>{const u=await api<User>('/workspace/switch','POST',{mode:user?.demo?'local':'demo'});setUser(u);setProfile(u.profile);setSettings(u.settings);setJobs([]);setApps([]);setStats(null);setSelected(null);setReview(null);setLiveId('');setProfileStep(0);setEditingProfile(false);setTab(u.profile.confirmed?'Overview':'My profile');});
 const navigate=(name:string)=>{const target=(name==='Jobs'||name==='Find Jobs')?'Find Jobs':name;if(target==='My profile'&&user?.profile.confirmed)setEditingProfile(true);setTab(user?.profile.confirmed?target:'My profile');setMobile(false);setQuery('');};
 const openReview=(a:Application)=>{setReview(a);setPack(structuredClone(a.package));setDocTab('resume');setEditDocument(false);setSelected(null)};
 const prepare=(j:Job)=>act(j.id,async()=>{const a=await api<Application>(`/jobs/${j.id}/prepare`,'POST');await refresh();openReview(a)});
 const control=(a:Application,action:string)=>act(action,async()=>{const updated=await api<Application>(`/applications/${a.id}/action`,'POST',{action});setLiveId(updated.id);await refresh()});
 const agentControl=(action:string)=>act('agent',async()=>{setAgent(await api<AgentState>('/agent/control','POST',{action}));await refresh()});
 const submitCheckpoint=async(checkpointType:string,value:string)=>act('checkpoint',async()=>{
  const updated=await api<AgentState>('/agent/checkpoint','POST',{checkpoint_type:checkpointType,value});
  setAgent(updated);setNotice(`Submitted ${checkpointType} to agent.`);await refresh();
 });
 const retryAgent=()=>act('retry',async()=>{
  const updated=await api<AgentState>('/agent/retry','POST');
  setAgent(updated);setNotice('Retrying agent run...');await refresh();
 });
 const testOpenRouter=async()=>{
  setTestOrBusy(true);setOrStatusText('');
  try{
   const r=await api<{connected:boolean;label?:string;usage?:number;limit?:number;error?:string}>('/integrations/test/openrouter','POST',{api_key:orKeyInput.trim()||undefined});
   setOrStatusText(r.connected?`Connected! ${r.label||'Active'}`:`Failed: ${r.error||'Invalid key'}`);
   await refresh();
  }catch(e:any){setOrStatusText(`Error: ${e.message}`)}
  finally{setTestOrBusy(false)}
 };
 const testBrowserbase=async()=>{
  setTestBbBusy(true);setBbStatusText('');
  try{
   const r=await api<{connected:boolean;error?:string}>('/integrations/test/browserbase','POST',{api_key:bbKeyInput.trim()||undefined});
   setBbStatusText(r.connected?'Connected! Cloud browser ready.':`Failed: ${r.error||'Invalid key'}`);
   await refresh();
  }catch(e:any){setBbStatusText(`Error: ${e.message}`)}
  finally{setTestBbBusy(false)}
 };
 const saveIntegrationKeys=async()=>{
  act('keys',async()=>{
   await api('/integrations/configure','POST',{openrouter_api_key:orKeyInput.trim()||undefined,browserbase_api_key:bbKeyInput.trim()||undefined});
   setNotice('API credentials updated.');setShowKeyConfig(false);await refresh();
  });
 };
 const [showInternshalaCreds,setShowInternshalaCreds]=useState(false);
 const [isEmailInput,setIsEmailInput]=useState('');
 const [isPwInput,setIsPwInput]=useState('');
 const [isCredsSaved,setIsCredsSaved]=useState(false);

 useEffect(()=>{
  api<{has_credentials:boolean;email:string}>('/connections/internshala/credentials').then(res=>{
   if(res.has_credentials){setIsCredsSaved(true);if(res.email)setIsEmailInput(res.email);}
  }).catch(()=>{});
 },[]);

 const saveInternshalaCreds=async()=>{
  if(!isEmailInput.trim()||!isPwInput.trim())return;
  act('is_creds',async()=>{
   await api('/connections/internshala/credentials','POST',{email:isEmailInput.trim(),password:isPwInput.trim()});
   setIsCredsSaved(true);setShowInternshalaCreds(false);
   setNotice('Internshala credentials saved locally! Agent will auto-login.');
   await refresh();
  });
 };
 const runJobDiscovery=async()=>{
  if(!customQuery.trim())return;
  setDiscoverBusy(true);
  try{
   const res=await api<{count:number;jobs:Job[]}>('/jobs/discover','POST',{query:customQuery.trim(),location:customLoc.trim(),is_remote:customRemote});
   setNotice(`Discovered ${res.count} vacancies!`);await refresh();
  }catch(e:any){setError(e.message)}
  finally{setDiscoverBusy(false)}
 };

 const [connecting,setConnecting]=useState<'LinkedIn'|'Indeed'|'Naukri'|'Internshala'|null>(null),[connectLive,setConnectLive]=useState('');
 const anyConnected=(integration?.sources||[]).length>0&&integration!.sources.some(s=>s.connected);
 const activePlatform=(settings?.source_focus==='indeed'?'Indeed':settings?.source_focus==='naukri'?'Naukri':settings?.source_focus==='internshala'?'Internshala':'LinkedIn');
 const platformConnected=!!integration?.sources.find(s=>s.name===activePlatform)?.connected;
 const canRunAgent=user?.demo||activePlatform==='Indeed'||platformConnected;
 const connectPlatform=async(name:'LinkedIn'|'Indeed'|'Naukri'|'Internshala')=>{
  if(connecting===name)return;
  setConnecting(name);
  try{
   const credCheck=await api<{has_credentials:boolean}>(`/connections/${name.toLowerCase()}/credentials`).catch(()=>({has_credentials:false}));
   if(credCheck.has_credentials){
    setNotice(`Auto-logging into ${name} with your saved credentials...`);
    const autoRes=await api<{connected:boolean;message?:string}>(`/connections/${name.toLowerCase()}/auto-login`,'POST').catch(()=>null);
    if(autoRes?.connected){
     setNotice(`Successfully connected to ${name}!`);
     setConnecting(null);
     await refresh();
     return;
    }
   }
   const r=await api<{connected:boolean;live_url:string|null}>(`/connections/${name.toLowerCase()}/check`,'POST');
   if(r.connected){
    setNotice(`Connected to ${name}!`);
    setConnecting(null);
    setConnectLive('');
    await refresh();
   }else{
    setConnectLive(r.live_url||'');
   }
  }catch(err:any){
   setError(err?.message||`Connection attempt failed for ${name}`);
   setConnecting(null);
  }
 };
 const cancelConnect=async()=>{
  if(connecting)await api(`/connections/${connecting.toLowerCase()}/cancel`,'POST').catch(()=>{});
  setConnecting(null);setConnectLive('');
 };
 useEffect(()=>{
  if(!connecting)return;
  let attempts=0;
  const poll=setInterval(async()=>{
   attempts++;
   if(attempts>8){
    setConnecting(null);
    return;
   }
   try{
    const r=await api<{connected:boolean;live_url:string|null}>(`/connections/${connecting.toLowerCase()}/check`,'POST');
    if(r.connected){setConnecting(null);setConnectLive('');await refresh()}else if(r.live_url)setConnectLive(r.live_url);
   }catch{}
  },2500);
  return()=>clearInterval(poll);
 },[connecting]);

  const handleArchiveJob = async (id: string) => {
    try {
      await api(`/jobs/${id}/archive`, 'POST');
      await refresh();
      setNotice('Job archive status updated.');
    } catch (err: any) {
      setError(err?.message || 'Failed to archive job');
    }
  };

  const handleDeleteJob = async (id: string) => {
    const target = jobs.find(j => j.id === id);
    if (!window.confirm(`Delete vacancy "${target?.title || 'this job'}"? This cannot be undone.`)) return;
    try {
      await api(`/jobs/${id}`, 'DELETE');
      await refresh();
      if (selected?.id === id) setSelected(null);
      setNotice('Vacancy removed.');
    } catch (err: any) {
      setError(err?.message || 'Failed to delete job');
    }
  };

  const clearClosedJobs = async () => {
    try {
      const res = await api<{ cleared: number; success: boolean }>('/jobs/clear-closed', 'POST');
      await refresh();
      setNotice(`Cleaned ${res.cleared} closed or invalid vacancies.`);
    } catch (err: any) {
      setError(err?.message || 'Failed to clean closed vacancies');
    }
  };

  const triggerFindJobs = async () => {
    if (discoveryRun?.status === 'running') return;
    setError('');
    try {
      const res = await api<{ run_id: string; status: string; phase: string }>('/jobs/find', 'POST');
      setDiscoveryRun({
        id: res.run_id,
        status: 'running',
        phase: res.phase,
        progress: {},
        events: [{ time: new Date().toISOString(), text: 'Started intelligent web research & job discovery...' }],
        results_count: 0
      });
      setNotice('Searching live openings matching your preferences across company career sites & portals...');
    } catch (err: any) {
      setError(err?.message || 'Could not start job discovery');
    }
  };

  const cancelFindJobs = async () => {
    try {
      await api('/jobs/discover/cancel', 'POST');
      setDiscoveryRun(prev => prev ? ({ ...prev, status: 'cancelled' }) : null);
      setNotice('Job discovery cancelled.');
    } catch (err: any) {
      setError(err?.message || 'Failed to cancel discovery');
    }
  };

  const verifyJobListing = async (jobId: string) => {
    try {
      const res = await api<{ id: string; status: string; verified_at: string; reason: string }>(`/jobs/${jobId}/verify`, 'POST');
      setNotice(`Listing status: ${res.status.toUpperCase()} (${res.reason})`);
      await refresh();
      if (selected && selected.id === jobId) {
        setSelected(prev => prev ? {
          ...prev,
          status: res.status,
          verified_at: res.verified_at,
          verification: { status: res.status === 'active' ? 'open' : res.status === 'closed' ? 'closed' : 'uncertain', verified_at: res.verified_at, reason: res.reason }
        } : null);
      }
    } catch (err: any) {
      setError(err?.message || 'Verification failed');
    }
  };

 const matched=jobs.filter(j=>j.match.matched), waiting=apps.filter(a=>a.status==='prepared'),live=apps.find(a=>a.id===liveId)||apps.find(a=>['running','paused','needs_input'].includes(a.status))||apps.find(a=>a.status==='approved')||apps[0];
 const loginApp=apps.find(a=>['prepared','approved','needs_input'].includes(a.status)&&a.human_reason==='login');
 const attentionApp=apps.find(a=>a.status==='needs_input');
 const handoffApp=loginApp||(agent.login_wait?undefined:attentionApp);const handoffLiveUrl=handoffApp?.live_url||agent.live_url;const agentActive=!!agent.id&&['running','paused','needs_input'].includes(agent.status);
 const humanAttention=agent.status==='needs_input'||!!loginApp||!!attentionApp;
 const loginAttention=!!loginApp||(agent.status==='needs_input'&&agent.human_reason==='login');
 const humanMessage=loginAttention?(loginApp?.status==='prepared'?'Sign in in Live View, then review and approve this application. No personal data has been entered by the agent.':'Sign in in Live View, then click Resume application. Your progress is saved; the agent will continue from that page.'):agent.events.at(-1)?.text||'Complete the requested step in Live View, then click Resume agent.';
 const humanNoticeKey=humanAttention?`${loginApp?.id||agent.id}:${loginApp?.events.at(-1)?.time||agent.events.at(-1)?.time}`:'';
 useEffect(()=>{if(humanNoticeKey&&humanNoticeKey!==humanNoticeSeen){setHumanNoticeSeen(humanNoticeKey);setNotice(loginAttention?'Login required. Agent paused—open Live View to sign in.':'Agent paused. Your input is needed in Live View.')}},[humanNoticeKey,humanNoticeSeen,loginAttention]);
 const focusedSource=activePlatform;
 const agentWaiting=waiting.filter(a=>!focusedSource||a.job.source===focusedSource);
 const visibleJobs=jobs.filter(j=>{
  if(filter==='Archived'){
   if(!j.archived)return false;
  }else{
   if(j.archived)return false;
  }
  if(query){
   const textMatch=`${j.company} ${j.title} ${(j.skills||[]).join(' ')} ${j.source} ${j.location}`.toLowerCase().includes(query.toLowerCase());
   if(!textMatch)return false;
  }
  const score=j.match?.score??0;
  if(minScoreFilter>0&&score<minScoreFilter)return false;
  if(sourceFilter!=='All'&&j.source.toLowerCase()!==sourceFilter.toLowerCase())return false;
  if(modeFilter!=='All'&&j.mode.toLowerCase()!==modeFilter.toLowerCase())return false;
  if(eligibilityFilter==='Eligible only'&&(j.match?.blockers||[]).length>0)return false;
  if(eligibilityFilter==='Needs review'&&(j.match?.unknown||[]).length===0)return false;

  if(filter==='Top matches')return !!j.match?.matched;
  if(filter==='Indeed')return j.source?.toLowerCase()==='indeed';
  if(filter==='LinkedIn')return j.source?.toLowerCase()==='linkedin';
  if(filter==='Naukri')return j.source?.toLowerCase()==='naukri';
  if(filter==='Internshala')return j.source?.toLowerCase()==='internshala';
  if(filter==='Remote')return j.mode?.toLowerCase()==='remote';
  if(filter==='Needs review')return (j.match?.unknown?.length||0)>0;
  return true;
 }).sort((a,b)=>{
  if(sortBy==='score_desc')return (b.match?.score||0)-(a.match?.score||0);
  if(sortBy==='score_asc')return (a.match?.score||0)-(b.match?.score||0);
  if(sortBy==='company_asc')return a.company.localeCompare(b.company);
  if(sortBy==='newest')return (b.posted||'').localeCompare(a.posted||'');
  return 0;
 });
 useEffect(()=>{const context=(document as unknown as {modelContext?:{registerTool:(tool:unknown,options:unknown)=>void}}).modelContext;if(!context)return;const lifecycle=new AbortController();try{context.registerTool({name:'navigate_job_workspace',description:'Open a visible section of the RapidSkills workspace. Does not submit applications.',inputSchema:{type:'object',properties:{section:{type:'string',enum:tabs.map(t=>t.name)}},required:['section'],additionalProperties:false},execute:async(input:{section:string})=>{if(!tabs.some(t=>t.name===input.section))throw Error('Unknown section');setTab(input.section);return {section:input.section}},annotations:{readOnlyHint:false}},{signal:lifecycle.signal})}catch{}return()=>lifecycle.abort()},[]);
 if(boot)return <div className="splash"><Orbit size={44}/><p>Opening your workspace…</p></div>;
 if(!user)return <div className="splash"><Orbit size={44}/><h2>Your workspace is almost ready.</h2><p>{error||'The backend is starting. Please try again.'}</p><button className="btn primary" onClick={()=>window.location.reload()}>Try again</button></div>;
 if(!user.profile.confirmed&&!editingProfile&&profile)return <><Onboarding initial={profile} onSave={async p=>{await api('/profile','PUT',p);setProfile(p);setUser({...user,profile:p,name:p.name});}} onComplete={()=>{setTab('Overview');refresh().catch(()=>{});setNotice('Profile confirmed. Welcome to your dashboard.')}}/></>;
 return <div className="workspace"><aside className={`sidebar ${mobile?'open':''} ${sidebarCollapsed?'collapsed':''}`}><div className="sidebar-header-row"><a className="brand brand-logo" onClick={()=>navigate('Overview')}><img src="/rapidskill-logo.png" alt="Rapidskill"/><small>AI Job Apply Agent</small></a><button type="button" className="sidebar-collapse-btn" aria-label="Collapse sidebar" title="Collapse sidebar (hide menu)" onClick={()=>setSidebarCollapsed(true)}><PanelLeftClose size={18}/></button></div><div className="workspace-name"><div className="avatar">{user.name.slice(0,1)||'Y'}</div><div><b>My workspace</b><small>Personal account</small></div><ChevronDown size={15}/></div><span className="nav-label">WORKSPACE</span><nav>{tabs.map(({name,icon:Icon},i)=><button key={name} className={`${tab===name?'active':''} ${name==='Preferences'?'nav-divider':''}`} onClick={()=>navigate(name)}><Icon size={19}/><span>{name}</span>{name==='Live agent'&&apps.some(a=>a.status==='running')&&<i className="live-dot"/>}</button>)}</nav><div className="sidebar-bottom"><div className="your-pace"><div className="pace-icon"><Sparkles size={19}/></div><b>Your search. Your pace.</b><p>A few great applications beat a hundred forgettable ones.</p><button onClick={()=>navigate('Preferences')}>Set your daily rhythm <ArrowUpRight size={15}/></button></div><button className="account" onClick={()=>navigate('My profile')}><div className="avatar lilac">{user.name.split(' ').map(n=>n[0]).join('').slice(0,2)}</div><span><b>{user.name||'Your workspace'}</b><small>Local workspace</small></span><UserRound size={17}/></button></div></aside><main className={`main ${sidebarCollapsed?'expanded':''}`}><header className="topbar"><div className="breadcrumb"><button type="button" className="icon-button sidebar-toggle-btn" aria-label={sidebarCollapsed?"Expand sidebar":"Collapse sidebar"} title={sidebarCollapsed?"Expand sidebar (show menu)":"Collapse sidebar"} onClick={()=>{if(mobile)setMobile(!mobile);else setSidebarCollapsed(!sidebarCollapsed);}}>{sidebarCollapsed ? <PanelLeftOpen size={20}/> : <Menu size={20}/>}</button><span>Workspace</span><span>/</span><b>{tab}</b></div><div className="topbar-right"><button className="demo-tag" disabled={!!busy} onClick={switchWorkspace}><Layers3 size={13}/>{user.demo?'Demo · Use my details':'My workspace · View demo'}<ArrowUpRight size={12}/></button><button className="icon-button" aria-label="Integration settings" onClick={()=>navigate('Preferences')}><Settings2 size={19}/></button><div className="avatar small">{user.name.slice(0,1)}</div></div></header>{error&&<div className="error-banner" role="alert"><AlertCircle size={18}/><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={()=>setError('')}><X size={17}/></button></div>}{notice&&<div className="toast" role="status"><CheckCircle2 size={18}/>{notice}</div>}<div className="content">{humanAttention&&<section className="human-alert" role="alert"><ShieldCheck size={22}/><div><b>{loginAttention?'Login required · Agent paused':'Your input is needed · Agent paused'}</b><p>{humanMessage}</p></div><button className="btn secondary" onClick={()=>{if(loginApp)setLiveId(loginApp.id);navigate('Live agent')}}>Open Live View<ArrowRight size={16}/></button></section>}
 {tab==='Overview'&&<><div className="page-heading"><div><span className="eyebrow">LET’S KEEP THINGS MOVING</span><h1>Your next move, {user.name.split(' ')[0]||'on your terms'}<span className="lime-period">.</span></h1><p>Less searching. More possibilities. Here’s where you stand.</p></div><button className="btn primary" onClick={()=>navigate('Live agent')}><Play size={18}/>Open agent</button></div><div className="section-title"><h2>Your search at a glance</h2><select aria-label="Analytics date range" value={days} onChange={e=>setDays(+e.target.value)}>{[7,30,90].map(d=><option key={d} value={d}>Last {d} days</option>)}</select></div><div className="stats-grid">{[{label:'Jobs discovered',value:stats?.discovered||0,icon:Search,note:'Unique opportunities',tone:'neutral'},{label:'Matched to you',value:stats?.matched||0,icon:Sparkles,note:'Passed your match criteria',tone:'lilac'},{label:'Applications sent',value:stats?.counts.submitted||0,icon:ArrowUpRight,note:user.demo?'Confirmed demo submissions':'Verified submissions only',tone:'lime'},{label:'Ready for review',value:stats?.counts.prepared||0,icon:FileText,note:'Your next move starts here',tone:'peach'}].map(({label,value,icon:Icon,note,tone})=><article className={`stat ${tone}`} key={label}><div><span>{label}</span><Icon size={19}/></div><strong>{value.toString().padStart(2,'0')}</strong><small>{note}</small></article>)}</div><div className="analytics-grid"><section className="panel activity-panel"><div className="panel-heading"><div><h2>A little progress, every day</h2><p>Your discovery and application activity</p></div><span className="legend"><i/>Discovered <i/>Applied</span></div><div className="chart"><div className="chart-axis">{[12,9,6,3,0].map(n=><span key={n}>{Math.round(n*Math.max(4,...(stats?.trend.map(d=>d.discovered)||[0]))/12)}</span>)}</div><div className="chart-plot"><div className="grid-lines"><i/><i/><i/><i/><i/></div><div className="bars">{stats?.trend.map(d=><div className="bar-group" key={d.day}><div className="bar-pair"><div title={`${d.discovered} discovered`} style={{height:`${Math.max(3,d.discovered/Math.max(4,...stats.trend.map(x=>x.discovered))*100)}%`}}/><div title={`${d.submitted} applied`} style={{height:`${Math.max(3,d.submitted/Math.max(4,...stats.trend.map(x=>x.discovered))*100)}%`}}/></div><span>{new Date(d.day+'T12:00:00').toLocaleDateString('en',{weekday:'short'})}</span></div>)}</div></div></div></section><section className="panel funnel-panel"><div className="panel-heading"><div><h2>From found to sent</h2><p>Every step brings you closer</p></div><ArrowUpRight size={19}/></div>{[{label:'Discovered',n:stats?.discovered||0},{label:'Evaluated',n:stats?.evaluated||0},{label:'Matched',n:stats?.matched||0},{label:'Prepared',n:stats?.packages||0},{label:'Applied',n:stats?.counts.submitted||0}].map((x,i)=><div className="funnel-row" key={x.label}><div><span><em>0{i+1}</em>{x.label}</span><b>{x.n}</b></div><div className="funnel-track"><i style={{width:`${x.n/Math.max(1,stats?.discovered||1)*100}%`,background:['#dedfe2','#d2c9ef','#b9a7eb','#a6c56b','#c2f970'][i]}}/></div></div>)}</section></div>{jobs.length>0&&<section className="panel" style={{marginTop:24}}><div className="panel-heading"><div><h2>Discovered Opportunities ({jobs.length})</h2><p>Live vacancies inspected by your agent from Indeed & LinkedIn</p></div><button className="btn secondary" style={{fontSize:'0.82rem',padding:'6px 14px'}} onClick={()=>navigate('Jobs')}>View all jobs ({jobs.length})<ArrowRight size={14}/></button></div><div className="job-grid discover">{jobs.slice(0,6).map(j=><JobCard key={j.id} job={j} onOpen={()=>setSelected(j)} onArchive={handleArchiveJob} onDelete={handleDeleteJob}/>)}</div></section>}</>}
 {tab==='Live agent'&&<><div className="page-heading"><div><span className="eyebrow">AUTOMATED JOB APPLICANT</span><h1>Live Agent</h1><p>Watch your agent search jobs, match your profile, and apply automatically on your favorite platforms.</p></div>{agent.status!=='idle'&&<span className="status-badge">{agent.status.replace('_',' ')}</span>}</div><div className="platform-selector-bar" style={{marginBottom:16}}><span className="selector-label">Platform Focus:</span>{(['LinkedIn','Indeed','Naukri','Internshala'] as const).map(p=>{const src=integration?.sources.find(s=>s.name===p);const isConn=!!src?.connected;const isSelected=activePlatform===p;return <div key={p} className="platform-pill-wrapper"><button type="button" className={`platform-pill ${isSelected?'active':''}`} onClick={async()=>{if(settings&&settings.source_focus!==p.toLowerCase()){const next={...settings,source_focus:p.toLowerCase() as 'linkedin'|'indeed'|'naukri'|'internshala'};setSettings(next);await api('/settings','PUT',next).catch(()=>{});await refresh();}}}><span className={`status-dot ${isConn?'online':'offline'}`}/><b>{p}</b><span className="pill-badge">{isConn?'Connected':p==='Indeed'?'Public search ready':'Not connected'}</span></button>{!isConn&&!user.demo&&<button type="button" className="btn ghost connect-mini-btn" disabled={!!busy||!!connecting} onClick={()=>connectPlatform(p)}>{connecting===p?'Connecting…':`Connect ${p}`}</button>}</div>;})}</div><AutoLoginVaultCard activePlatform={activePlatform} onPlatformChange={async (p)=>{const slug=p.toLowerCase() as 'linkedin'|'indeed'|'naukri'|'internshala';if(settings&&settings.source_focus!==slug){const next={...settings,source_focus:slug};setSettings(next);await api('/settings','PUT',next);await refresh();}}} onConnect={async (p)=>{await connectPlatform(p as any);}} isAgentRunning={['running','paused','needs_input'].includes(agent.status)}/>{connecting && (
  connectLive ? (
    <div className="connect-live" style={{margin:'16px 0'}}>
      <LiveFrame title={`Sign in to ${connecting}`} src={connectLive} interactive/>
      <button type="button" className="btn ghost" disabled={!!busy} onClick={cancelConnect}><Square size={14}/>Cancel</button>
    </div>
  ) : (
    <ConnectingProgressCard platform={connecting} onCancel={cancelConnect}/>
  )
)}{connectionLost&&<div role="alert" className="info-box">Backend connection lost. Displayed progress may be stale. Reconnecting automatically.</div>}{live?.human_reason==='access'&&<div role="alert" className="info-box">{live.events.at(-1)?.text}</div>}{agentWaiting.length>0&&(
  <section className="review-action-banner" role="region" aria-label="Applications awaiting approval" style={{marginTop:16}}>
    <div className="banner-pulse-icon">
      <span className="pulse-beacon"/>
      <FileText size={22}/>
    </div>
    <div className="banner-text-content">
      <div className="banner-badge-row">
        <span className="banner-action-tag">ACTION REQUIRED</span>
        <span className="banner-count-tag">{agentWaiting.length} Ready to Send</span>
      </div>
      <h3>{agentWaiting.length} Application{agentWaiting.length>1?'s':''} Awaiting Your Review & Approval</h3>
      <p>Tailored resume bullets & personalized cover letter are prepared. Review the application package to authorize final submission.</p>
    </div>
    <button className="btn primary banner-cta-btn" onClick={()=>openReview(agentWaiting[0])}>
      <span>Review Application</span>
      <ArrowRight size={17}/>
    </button>
  </section>
)}{(agent.needed?.length||0)>0&&<div className="info-box needs-box" style={{marginTop:16}}><div><b>The agent skipped jobs because it needs {agent.needed!.length} answer{agent.needed!.length>1?'s':''} from you</b><ul>{agent.needed!.slice(0,6).map(n=><li key={n.question}>{n.question}<small> · {n.job}</small></li>)}</ul><p>It never guesses about you. Add the answer to your profile (years per skill, or an approved answer) and it retries those jobs on the next run.</p></div><button className="btn primary" onClick={()=>setTab('My profile')}>Add answers</button></div>}<div className="panel" style={{marginTop:16,padding:'18px 22px',borderRadius:12}}><div className="agent-summary" style={{margin:0}}><div><span className="eyebrow">AGENT STATUS</span><h2 style={{margin:'4px 0 6px',fontSize:'1.25rem'}}>{agent.status==='idle'?'Ready to Start':`${agent.status.replace('_',' ')} · ${agent.phase}`}</h2><p style={{margin:0,fontSize:'0.84rem',color:'#6b7280'}}>{settings?.matching==='fresher_ai'?`${profile?.roles} and closely related roles · ${profile?.country} · All locations and work modes · Fit ${settings?.effective_threshold??60}% or better`:`${profile?.roles} · ${profile?.country} · ${profile?.locations} · ${profile?.work_modes.join(' / ')}`}</p></div><div className="browser-controls">{['idle','completed','stopped','failed'].includes(agent.status)&&<button className="btn primary" disabled={!!busy||(!user.demo&&!platformConnected&&activePlatform!=='Indeed')} onClick={()=>agentControl('start')}><Play size={16}/>{canRunAgent?`Start ${activePlatform} agent`:`Connect ${activePlatform} to start`}</button>}{agent.status==='running'&&<button className="btn secondary" disabled={!!busy} onClick={()=>agentControl('pause')}><Pause size={16}/>Pause agent</button>}{['running','paused'].includes(agent.status)&&<button className="btn secondary" disabled={!!busy} onClick={()=>agentControl('takeover')}><MousePointer2 size={16}/>Take control</button>}{['paused','needs_input','failed'].includes(agent.status)&&<button className="btn primary" disabled={!!busy} onClick={()=>agentControl('resume')}><Play size={16}/>Resume agent</button>}{['running','paused','needs_input'].includes(agent.status)&&<button className="btn ghost" disabled={!!busy} onClick={()=>agentControl('stop')}><Square size={16}/>Stop agent</button>}</div></div><div className="agent-metrics" style={{marginTop:14,paddingTop:14,borderTop:'1px solid #f1f5f9'}}><span><b>{agent.searched||0}</b> searches</span><span><b>{agent.candidate_pages||0}</b> candidate pages</span><span><b>{agent.inspected||0}</b> inspected</span><span><b>{matched.length}</b> matches across runs</span><span><b>{agentWaiting.length}</b> awaiting review</span>{(agent.prefiltered||0)>0&&<span><b>{agent.prefiltered}</b> skipped before model call</span>}{agent.spend&&agent.spend.calls>0&&<span>Model spend ${agent.spend.usd.toFixed(2)} of ${agent.spend.cap.toFixed(2)} limit</span>}</div></div><div className="live-layout discovery-layout" style={{marginTop:16}}><section className="browser-panel"><div className="browser-chrome"><Radio size={16}/><span>{handoffApp?`${handoffApp.job.company} application · ${handoffApp.human_reason==='login'?'sign in here':'needs you here'}`:agent.login_wait?'Agent browser · sign in here':`${activePlatform} Live Browser`}</span></div>{handoffLiveUrl&&/^https:\/\/([a-z0-9-]+\.)*browserbase\.com\//i.test(handoffLiveUrl)&&['running','paused','needs_input'].includes(agent.status)?<LiveFrame title="Live agent job discovery" src={handoffLiveUrl} interactive={agent.status==='needs_input'}/>:<Empty title={agent.status==='completed'?'Search finished':agent.status==='failed'?'Agent needs attention':['running','paused','needs_input','searching'].includes(agent.status)?`${activePlatform} Desktop Browser Active`:`${activePlatform} Browser Ready`} body={agent.status==='failed'?(agent.events.at(-1)?.text||'Review the activity log, resolve the issue, then resume.'):['running','paused','needs_input','searching'].includes(agent.status)?'A real Chrome browser window is running on your desktop. You can see it live, and every step is logged below.':`Click 'Start ${activePlatform} Agent' or 'Save & Auto-Login' to launch the browser.`}/>}</section><aside className="event-panel"><div className="panel-heading"><h2>Agent activity</h2><span>{agent.events.length}</span></div><div className="timeline agent-timeline">{agent.events.length===0?<p style={{padding:'20px 16px',color:'#94a3b8',fontSize:'0.84rem',textAlign:'center'}}>No events recorded yet. Start the agent to see real-time progress.</p>:agent.events.slice().reverse().map((e,i)=><div className="timeline-event" key={i}><div className="timeline-icon"><Check size={12}/></div><div><p>{e.text}</p><small>{new Date(e.time).toLocaleTimeString()}</small></div></div>)}</div></aside></div>{agent.plan&&<PlanPanel plan={agent.plan} spent={agent.spend?.usd}/>}{agent.shortlist&&agent.shortlist.length>0&&<ShortlistPanel items={agent.shortlist} version={agent.ranking_version}/>}{agent.trace&&agent.trace.length>0&&<TracePanel trace={agent.trace}/>}</>}
  {(tab==='Find Jobs'||tab==='Jobs')&&<>
    <div className="page-heading">
      <div>
        <span className="eyebrow">INTELLIGENT JOB DISCOVERY</span>
        <h1>Find Jobs ({visibleJobs.length})</h1>
        <p>Live job discovery across Naukri, Internshala, LinkedIn, Indeed, and top company career boards matching your profile.</p>
      </div>
      <div style={{display:'flex',gap:10,flexWrap:'wrap',alignItems:'center'}}>
        <button className="btn secondary" onClick={clearClosedJobs} title="Remove closed, expired, or invalid vacancies">
          <Trash2 size={15}/>Clean closed
        </button>
        {discoveryRun?.status==='running' ? (
          <button className="btn secondary" style={{color:'#ef4444',borderColor:'#fca5a5',display:'inline-flex',alignItems:'center',gap:6}} onClick={cancelFindJobs}>
            <Square size={15}/>Cancel search
          </button>
        ) : (
          <button 
            className="btn primary" 
            onClick={triggerFindJobs} 
            disabled={busy==='find_jobs'}
            style={{ minWidth: 150, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
          >
            {busy==='find_jobs' ? <LoaderCircle className="spin" size={16}/> : <Search size={16}/>}
            {busy==='find_jobs' ? 'Searching...' : 'Find Jobs Now'}
          </button>
        )}
      </div>
    </div>

    {/* Saved Preferences Summary Banner */}
    <div className="panel" style={{marginBottom:18,padding:'12px 18px',borderRadius:12,background:'#f8fafc',border:'1px solid #e2e8f0',display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:12}}>
      <div style={{display:'flex',gap:16,alignItems:'center',flexWrap:'wrap'}}>
        <div>
          <span style={{fontSize:'0.72rem',textTransform:'uppercase',fontWeight:700,color:'#64748b',letterSpacing:'0.05em',display:'block'}}>Active Profile Criteria</span>
          <span style={{fontSize:'0.9rem',fontWeight:600,color:'#1e293b'}}>
            {profile?.roles || 'All Software Roles'} &bull; {profile?.locations || profile?.country || 'Anywhere'} &bull; {profile?.work_modes?.join('/') || 'Any Mode'}
          </span>
        </div>
        <div style={{height:28,width:1,background:'#cbd5e1'}}/>
        <div>
          <span style={{fontSize:'0.72rem',textTransform:'uppercase',fontWeight:700,color:'#64748b',letterSpacing:'0.05em',display:'block'}}>Experience & Threshold</span>
          <span style={{fontSize:'0.88rem',color:'#334155'}}>
            {profile?.experience || 'All levels'} &bull; Min {settings?.threshold ?? settings?.effective_threshold ?? 60}% Match
          </span>
        </div>
      </div>
      <button className="btn ghost" style={{fontSize:'0.82rem',padding:'4px 8px'}} onClick={()=>setTab('Preferences')}>
        <SlidersHorizontal size={14}/>Edit Preferences
      </button>
    </div>

    {/* Elegant Active Loading State */}
    {discoveryRun && discoveryRun.status==='running' && (
      <div style={{
        marginBottom: 20,
        padding: '16px 20px',
        borderRadius: 12,
        border: '1px solid #bfdbfe',
        background: '#ffffff',
        boxShadow: '0 4px 16px rgba(37,99,235,0.08)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 16,
        flexWrap: 'wrap'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 40, height: 40, borderRadius: '50%', background: '#eff6ff', display: 'grid', placeItems: 'center', color: '#2563eb', flexShrink: 0 }}>
            <LoaderCircle className="spin" size={22}/>
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '0.98rem', fontWeight: 650, color: '#1e3a8a' }}>
              Finding jobs across Naukri, Internshala, LinkedIn, Indeed & ATS boards...
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '0.82rem', color: '#64748b' }}>
              {discoveryRun.events && discoveryRun.events.length > 0
                ? discoveryRun.events[discoveryRun.events.length - 1].text
                : 'Scraping live vacancies matching your roles & skills in the background...'}
            </p>
          </div>
        </div>
        <button className="btn secondary" style={{ padding: '6px 12px', fontSize: '0.8rem', borderColor: '#cbd5e1' }} onClick={cancelFindJobs}>
          Cancel
        </button>
      </div>
    )}

    {/* Filter and Search Bar */}
    <div className="section-title" style={{gap:10,flexWrap:'wrap',alignItems:'center',display:'flex',marginBottom:12}}>
      <div className="search-field" style={{display:'flex',alignItems:'center',gap:8,background:'#fff',border:'1px solid #dde0e6',borderRadius:10,padding:'7px 14px',flex:1,minWidth:240}}>
        <Search size={16} color="#888"/>
        <input style={{border:'none',padding:0,outline:'none',width:'100%',fontSize:'0.88rem'}} placeholder="Filter by title, company, skills..." value={query} onChange={e=>setQuery(e.target.value)}/>
        {query&&<button style={{border:'none',background:'none',padding:0,cursor:'pointer'}} onClick={()=>setQuery('')}><X size={15}/></button>}
      </div>

      <select value={sourceFilter} onChange={e=>setSourceFilter(e.target.value)} style={{padding:'8px 12px',borderRadius:8,border:'1px solid #cbd5e1',fontSize:'0.84rem',background:'#fff'}}>
        <option value="All">All Sources</option>
        <option value="Naukri">Naukri</option>
        <option value="Internshala">Internshala</option>
        <option value="LinkedIn">LinkedIn</option>
        <option value="Indeed">Indeed</option>
        <option value="Greenhouse">Greenhouse</option>
        <option value="Lever">Lever</option>
        <option value="Ashby">Ashby</option>
        <option value="Company Careers">Company Careers</option>
      </select>

      <select value={modeFilter} onChange={e=>setModeFilter(e.target.value)} style={{padding:'8px 12px',borderRadius:8,border:'1px solid #cbd5e1',fontSize:'0.84rem',background:'#fff'}}>
        <option value="All">All Modes</option>
        <option value="Remote">Remote only</option>
        <option value="Hybrid">Hybrid</option>
        <option value="Onsite">Onsite</option>
      </select>

      <select value={sortBy} onChange={e=>setSortBy(e.target.value)} style={{padding:'8px 12px',borderRadius:8,border:'1px solid #cbd5e1',fontSize:'0.84rem',background:'#fff'}}>
        <option value="score_desc">Highest Match Score</option>
        <option value="recent">Most Recently Discovered</option>
        <option value="company_asc">Company (A-Z)</option>
      </select>

      <div style={{display:'flex',alignItems:'center',gap:8,background:'#fff',padding:'5px 12px',borderRadius:8,border:'1px solid #cbd5e1'}}>
        <span style={{fontSize:'0.78rem',color:'#64748b'}}>Min Fit:</span>
        <input type="range" min={0} max={100} step={5} value={minScoreFilter} onChange={e=>setMinScoreFilter(Number(e.target.value))} style={{width:80}}/>
        <b style={{fontSize:'0.82rem',minWidth:32}}>{minScoreFilter}%</b>
      </div>
    </div>

    {/* Quick filter pills */}
    <div className="pills" style={{marginBottom:18,display:'flex',gap:6,flexWrap:'wrap'}}>
      {(['All jobs','Top matches','Naukri','Internshala','LinkedIn','Indeed','Greenhouse','Lever','Ashby','Remote','Needs review','Archived'] as const).map(f=>(
        <button key={f} className={filter===f?'active':''} onClick={()=>setFilter(f)}>{f}</button>
      ))}
    </div>

    {/* Job Grid / Empty state */}
    {visibleJobs.length===0 ? (
      <Empty
        title="No jobs match your filter"
        body={jobs.length===0 ? "Click 'Find Jobs Now' to launch intelligent web discovery based on your profile roles and preferences." : "Try adjusting your search query, source filter, or lowering the minimum match slider."}
      />
    ) : (
      <div className="job-grid discover">
        {visibleJobs.map(j=>(
          <JobCard
            key={j.id}
            job={j}
            onOpen={()=>setSelected(j)}
            onArchive={handleArchiveJob}
            onDelete={handleDeleteJob}
            onVerify={verifyJobListing}
          />
        ))}
      </div>
    )}
  </>}
 {tab==='Applications'&&<TrackerView apps={apps} api={api} Badge={Badge} onError={setError} onRefresh={refresh} onControl={(id,action)=>{const a=apps.find(x=>x.id===id);if(a)control(a,action)}} onReview={id=>{const a=apps.find(x=>x.id===id);if(a)openReview(a)}}/>}
 {tab==='My profile'&&profile&&<Onboarding initial={profile} editing onSave={async p=>{await api('/profile','PUT',p);setProfile(p);setUser({...user,profile:p,name:p.name});}} onComplete={()=>{setTab('Overview');refresh().catch(()=>{});setNotice('Profile confirmed. Welcome to your dashboard.')}}/>}
 {tab==='Preferences'&&settings&&<><div className="page-heading"><div><span className="eyebrow">YOU SET THE DIRECTION</span><h1>Your search. Your rules.</h1><p>Choose how much to hand off and where to stay hands-on.</p></div><button className="btn primary" disabled={!!busy} onClick={()=>act('settings',async()=>{await api('/settings','PUT',settings);setUser({...user,settings});await refresh();setNotice('Preferences saved.')})}><Check size={17}/>Save preferences</button></div><section className="panel settings-panel"><h2>Job sources</h2><p className="muted">Choose which job network the autonomous agent searches and applies to:</p><div className="approval-modes" style={{marginBottom:18}}>{[{id:'linkedin',title:'LinkedIn Easy Apply',desc:'Searches 1-click Easy Apply postings on LinkedIn.',icon:Globe2},{id:'indeed',title:'Indeed Apply',desc:'Searches 1-click Apply now / Easily apply vacancies on Indeed.',icon:Sparkles},{id:'naukri',title:'Naukri Apply',desc:'Searches 1-click Apply on Naukri vacancies across India.',icon:Globe2},{id:'internshala',title:'Internshala Apply',desc:'Searches internships and fresher jobs on Internshala.',icon:Globe2}].map(({id,title,desc,icon:Icon})=><button key={id} className={settings.source_focus===id?'selected':''} onClick={()=>setSettings({...settings,source_focus:id as 'linkedin'|'indeed'|'naukri'|'internshala'})}><div><Icon size={23}/><span className="radio-circle">{settings.source_focus===id&&<i/>}</span></div><b>{title}</b><p>{desc}</p></button>)}</div><h2>Job matching</h2><label className="check-label"><input type="checkbox" checked={settings.matching==='fresher_ai'} onChange={e=>setSettings({...settings,matching:e.target.checked?'fresher_ai':'strict'})}/>Widen my target roles to closely related ones across my target country</label><p className="muted">Searches your own roles first, then closely related ones, in any city or work mode. The minimum match score still applies. Required experience and explicit eligibility restrictions still apply; unstated sponsorship is flagged for review.</p><h2>How would you like to apply?</h2><p className="muted">Every mode pauses when the agent needs information only you can provide.</p><div className="approval-modes">{[{id:'each',title:'One at a time',desc:'Review and approve every tailored application.',icon:FileText},{id:'batch',title:'A curated batch',desc:'Review a set of applications and approve them together.',icon:Layers3},{id:'automatic',title:'On your terms',desc:'Automatically submit within your saved rules and limits.',icon:Sparkles}].map(({id,title,desc,icon:Icon})=><button className={settings.mode===id?'selected':''} key={id} onClick={()=>setSettings({...settings,mode:id,auto_enabled:false})}><div><Icon size={23}/><span className="radio-circle">{settings.mode===id&&<i/>}</span></div><b>{title}</b><p>{desc}</p></button>)}</div>{settings.mode==='automatic'&&<label className="check-label"><input type="checkbox" checked={settings.auto_enabled} onChange={e=>setSettings({...settings,auto_enabled:e.target.checked})}/>Allow automatic submission of truthful application packages that meet my saved criteria.</label>}<div className="settings-limits"><label>Daily application limit<input type="number" min={1} max={10} value={settings.daily_limit} onChange={e=>setSettings({...settings,daily_limit:+e.target.value})}/><small>A few highly tailored applications each day.</small></label><label>Minimum match score<div className="range-field"><input type="range" min={0} max={100} value={settings.threshold??settings.effective_threshold??70} onChange={e=>setSettings({...settings,threshold:+e.target.value})}/><b>{settings.threshold??settings.effective_threshold??70}%</b></div><small>{settings.threshold===null?'Default for your career level (60% fresher, 70% experienced) until you move the slider. ':''}Required preferences always come first.</small></label></div></section><section className="panel settings-panel"><div className="panel-heading"><div><h2>Your connections & credentials</h2><p>Real-time verification and API status.</p></div><div style={{display:'flex',gap:8}}><button className="btn secondary" style={{padding:'4px 10px',fontSize:'0.78rem'}} onClick={()=>setShowKeyConfig(!showKeyConfig)}>{showKeyConfig?'Close keys':'Configure keys'}</button><button className="icon-button" aria-label="Refresh connection status" onClick={()=>refresh().catch(e=>setError(e.message))}><RefreshCw size={17}/></button></div></div>{showKeyConfig&&<div style={{background:'#f7f8fa',padding:14,borderRadius:10,marginBottom:16,border:'1px solid #e1e3ea'}}><h4 style={{margin:'0 0 8px',fontSize:'0.88rem'}}>Configure Service Credentials</h4><div style={{display:'flex',flexDirection:'column',gap:10}}><label style={{fontSize:'0.82rem'}}>OpenRouter API Key<input type="password" style={{width:'100%',padding:'6px 10px',borderRadius:6,border:'1px solid #ccc',fontSize:'0.82rem'}} placeholder="sk-or-v1-..." value={orKeyInput} onChange={e=>setOrKeyInput(e.target.value)}/></label><label style={{fontSize:'0.82rem'}}>Browserbase API Key<input type="password" style={{width:'100%',padding:'6px 10px',borderRadius:6,border:'1px solid #ccc',fontSize:'0.82rem'}} placeholder="bb_api_..." value={bbKeyInput} onChange={e=>setBbKeyInput(e.target.value)}/></label><button className="btn primary" style={{alignSelf:'flex-start',fontSize:'0.82rem',padding:'6px 12px'}} onClick={saveIntegrationKeys}><Check size={14}/>Save credentials</button></div></div>}<div className="connection-row"><div className="connection-icon"><Sparkles/></div><div><b>DeepSeek via OpenRouter</b><small>{integration?.model}</small>{orStatusText&&<small style={{display:'block',color:'#166534'}}>{orStatusText}</small>}</div><div style={{display:'flex',alignItems:'center',gap:8}}><span className={`connection-status ${integration?.openrouter?'connected':''}`}>{integration?.openrouter?'Key configured':'Key needed'}</span><button type="button" className="btn secondary" style={{padding:'4px 10px',fontSize:'0.78rem'}} disabled={testOrBusy} onClick={testOpenRouter}>{testOrBusy?'Testing...':'Test connection'}</button></div></div><div className="connection-row"><div className="connection-icon lilac"><Globe2/></div><div><b>Browserbase Cloud Browser</b><small>Cloud browser · Live View · Human takeover</small>{bbStatusText&&<small style={{display:'block',color:'#166534'}}>{bbStatusText}</small>}</div><div style={{display:'flex',alignItems:'center',gap:8}}><span className={`connection-status ${integration?.browserbase?'connected':''}`}>{integration?.browserbase?'Key configured':'Key needed'}</span><button type="button" className="btn secondary" style={{padding:'4px 10px',fontSize:'0.78rem'}} disabled={testBbBusy} onClick={testBrowserbase}>{testBbBusy?'Testing...':'Test connection'}</button></div></div><div className="connection-row"><div className="connection-icon"><Globe2/></div><div><b>LinkedIn</b><small>Job search & 1-click Easy Apply</small></div><div style={{display:'flex',alignItems:'center',gap:8}}><span className={`connection-status ${integration?.sources.find(s=>s.name==='LinkedIn')?.connected?'connected':''}`}>{integration?.sources.find(s=>s.name==='LinkedIn')?.connected?'Connected':'Not connected'}</span>{!integration?.sources.find(s=>s.name==='LinkedIn')?.connected&&<button type="button" className="btn secondary" style={{padding:'4px 10px',fontSize:'0.78rem'}} onClick={()=>connectPlatform('LinkedIn')}>Connect</button>}</div></div><div className="connection-row"><div className="connection-icon lilac"><Sparkles/></div><div><b>Indeed</b><small>Job search & 1-click Indeed Apply</small></div><div style={{display:'flex',alignItems:'center',gap:8}}><span className={`connection-status ${integration?.sources.find(s=>s.name==='Indeed')?.connected?'connected':''}`}>{integration?.sources.find(s=>s.name==='Indeed')?.connected?'Connected':'Not connected'}</span>{!integration?.sources.find(s=>s.name==='Indeed')?.connected&&<button type="button" className="btn secondary" style={{padding:'4px 10px',fontSize:'0.78rem'}} onClick={()=>connectPlatform('Indeed')}>Connect</button>}</div></div><div className="connection-row"><div className="connection-icon"><Globe2/></div><div><b>Naukri</b><small>Job search & 1-click Apply on Naukri</small></div><div style={{display:'flex',alignItems:'center',gap:8}}><span className={`connection-status ${integration?.sources.find(s=>s.name==='Naukri')?.connected?'connected':''}`}>{integration?.sources.find(s=>s.name==='Naukri')?.connected?'Connected':'Not connected'}</span>{!integration?.sources.find(s=>s.name==='Naukri')?.connected&&<button type="button" className="btn secondary" style={{padding:'4px 10px',fontSize:'0.78rem'}} onClick={()=>connectPlatform('Naukri')}>Connect</button>}</div></div><div className="connection-row"><div className="connection-icon lilac"><Globe2/></div><div><b>Internshala</b><small>Internships & fresher jobs{isCredsSaved?' · Auto-login saved':''}</small></div><div style={{display:'flex',alignItems:'center',gap:8}}><button type="button" className="btn secondary" style={{padding:'4px 10px',fontSize:'0.78rem'}} onClick={()=>setShowInternshalaCreds(!showInternshalaCreds)}>{showInternshalaCreds?'Close Login':'Auto-Login Setup'}</button><span className={`connection-status ${integration?.sources.find(s=>s.name==='Internshala')?.connected?'connected':''}`}>{integration?.sources.find(s=>s.name==='Internshala')?.connected?'Connected':'Not connected'}</span>{!integration?.sources.find(s=>s.name==='Internshala')?.connected&&<button type="button" className="btn secondary" style={{padding:'4px 10px',fontSize:'0.78rem'}} onClick={()=>connectPlatform('Internshala')}>Connect</button>}</div></div>{showInternshalaCreds&&<div style={{background:'#f7f8fa',padding:14,borderRadius:10,marginBottom:16,border:'1px solid #e1e3ea'}}><h4 style={{margin:'0 0 8px',fontSize:'0.88rem'}}>Save Internshala Login for Auto-Login</h4><p style={{fontSize:'0.78rem',color:'#555',margin:'0 0 10px'}}>Credentials are stored locally in your database. The agent will paste them into the Internshala login form automatically.</p><div style={{display:'flex',flexDirection:'column',gap:10}}><label style={{fontSize:'0.82rem'}}>Internshala Email<input type="email" style={{width:'100%',padding:'6px 10px',borderRadius:6,border:'1px solid #ccc',fontSize:'0.82rem'}} placeholder="student@example.com" value={isEmailInput} onChange={e=>setIsEmailInput(e.target.value)}/></label><label style={{fontSize:'0.82rem'}}>Internshala Password<input type="password" style={{width:'100%',padding:'6px 10px',borderRadius:6,border:'1px solid #ccc',fontSize:'0.82rem'}} placeholder="••••••••" value={isPwInput} onChange={e=>setIsPwInput(e.target.value)}/></label><button className="btn primary" style={{alignSelf:'flex-start',fontSize:'0.82rem',padding:'6px 12px'}} onClick={saveInternshalaCreds}><Check size={14}/>Save & Auto-Login</button></div></div>}<p className="connection-help">API keys and credentials are saved safely on your local machine.</p></section><section className="panel settings-panel"><h2>Job sources</h2><p className="muted">RapidSkills supports LinkedIn Easy Apply, Indeed Apply, Naukri Apply, and Internshala Apply. Sign-in and verification always happen in Live View.</p><div className="sources-grid">{integration?.sources.map(s=><div key={s.name}><b>{s.name}</b><span className={s.enabled?'connected':''}>{s.enabled?'Available now':'Coming next'}</span></div>)}</div></section></>}
 </div><footer className="main-footer"><span>RapidSkills AI Job Apply Agent · a little momentum goes a long way</span><span>{user.demo?'Demo data · No real applications':'Private by design'}</span></footer></main>
 {selected&&<div className="drawer-backdrop" onClick={()=>setSelected(null)}><section className="drawer" role="dialog" aria-modal="true" aria-label="Job details" onClick={e=>e.stopPropagation()}><button className="close icon-button" aria-label="Close job details" onClick={()=>setSelected(null)}><X size={21}/></button><Logo job={selected} large/><span className="eyebrow">{selected.company} · {selected.source}</span><h2>{selected.title}</h2><p className="muted">{selected.location} · {selected.mode}</p><div className="match-detail"><div><Sparkles size={20}/><b>{selected.match.score}% fit</b></div><span>{selected.match.method}</span></div>{selected.match.recommendation&&<div className="info-box" style={{background:'#f0fdf4',border:'1px solid #bbf7d0',color:'#166534',fontWeight:600}}>Recommendation: {selected.match.recommendation}</div>}{selected.match.explanation&&<p className="info-box">{selected.match.explanation}</p>}{selected.match.experience_alignment&&<div className="info-box vertical"><b>Experience & Seniority</b><span>{selected.match.experience_alignment}</span></div>}{selected.match.location_alignment&&<div className="info-box vertical"><b>Location & Work Mode</b><span>{selected.match.location_alignment}</span></div>}{selected.match.salary_alignment&&<div className="info-box vertical"><b>Compensation Alignment</b><span>{selected.match.salary_alignment}</span></div>}<h3>Skills in common</h3><div className="skill-tags">{selected.match.matched_skills.map(s=><span key={s}><Check size={13}/>{s}</span>)}</div>{selected.match.blockers.length>0&&<div className="detail-warning"><b>Required preferences not met</b>{selected.match.blockers.map(s=><p key={s}>{s}</p>)}</div>}{selected.match.unknown.length>0&&<div className="info-box vertical"><b>Before you apply</b>{selected.match.unknown.map(s=><span key={s}>{s}</span>)}</div>}{selected.match.review_notes?.map((note,i)=><p className="info-box" key={i}>{note}</p>)}{selected.match.evaluation&&<section className="career-report"><h3>Career Ops evaluation · {selected.match.evaluation.global_score}/5</h3>{(['A','C','D','E','F','G','H'] as const).map((key,i)=><details key={key}><summary>{key} · {['Role summary','Seniority fit','Advertised compensation','Tailoring plan','Interview preparation','Posting risks','Screening questions'][i]}</summary><p>{selected.match.evaluation![key]}</p></details>)}<h3>B · Requirements and evidence</h3>{selected.match.evaluation.B.map((row,i)=><div className="info-box vertical" key={i}><b>{row.requirement} · {row.match}</b><span>{row.importance} importance · {row.tier} evidence</span>{row.jd_evidence&&<span>Employer: “{row.jd_evidence}”</span>}<span>Profile: {row.profile_evidence||'No confirmed evidence found'}</span></div>)}</section>}<h3>About the role</h3><div className="job-description">{selected.description}</div><div className="info-box"><CircleHelp size={19}/><p>Match scores estimate fit. They are not an employer’s ATS score.</p></div><div className="drawer-actions">{!selected.demo&&<><button className="btn secondary" disabled={!!busy} onClick={()=>act('match',async()=>{const match=await api<Match>(`/jobs/${selected.id}/match`,'POST');setSelected({...selected,match});await refresh()})}><Sparkles size={16}/>AI Fit Match</button><button className="btn secondary" disabled={!!busy} onClick={()=>act('assess',async()=>{const match=await api<Match>(`/jobs/${selected.id}/assess`,'POST');setSelected({...selected,match});await refresh()})}><Sparkles size={16}/>Career Ops</button></>}<button className="btn primary" disabled={!!busy} onClick={()=>prepare(selected)}>{busy===selected.id?<LoaderCircle className="spin" size={17}/>:<FileText size={17}/>}Prepare application</button>{selected.url&&<a className="btn ghost" href={selected.url} target="_blank" rel="noreferrer">Original listing<ExternalLink size={15}/></a>}{selected.id&&<><button className="btn ghost" disabled={!!busy} onClick={async()=>{await handleArchiveJob(selected.id);setSelected(null);}}><Archive size={15}/>{selected.archived?'Unarchive':'Archive'}</button><button className="btn ghost danger" disabled={!!busy} style={{color:'#ef4444'}} onClick={async()=>{await handleDeleteJob(selected.id);}}><Trash2 size={15}/>Delete</button></>}</div></section></div>}
 {review&&pack&&<div className="modal-backdrop" onClick={()=>setReview(null)}><section className="review-modal" role="dialog" aria-modal="true" aria-label="Review application" onClick={e=>e.stopPropagation()}><div className="review-heading"><div className="app-job"><Logo job={review.job}/><div><h2>{review.job.title}</h2><p>{review.job.company} · Application package</p></div></div><button className="icon-button" aria-label="Close application review" onClick={()=>setReview(null)}><X size={22}/></button></div><div className="review-toolbar"><div className="pills">{(['resume','cover_letter','recruiter_message'] as const).map(t=><button key={t} className={docTab===t?'active':''} onClick={()=>setDocTab(t)}>{t==='resume'?'Resume':t==='cover_letter'?'Cover letter':'Recruiter message'}</button>)}</div>{pack.diff&&<button className={`text-button document-mode ${showDiff?'active':''}`} onClick={()=>setShowDiff(!showDiff)}>{showDiff?'Hide diff':'View diff'}</button>}<a className="text-button" href={`/api/applications/${review.id}/download?kind=${docTab}`}><Download size={16}/>Download saved DOCX</a><a className="text-button" href={`/api/applications/${review.id}/download?kind=${docTab}&format=pdf`}><Download size={16}/>Download PDF</a></div>{['prepared','approved'].includes(review.status)&&<button className="text-button document-mode" disabled={!!busy} onClick={()=>act('materials',async()=>{const mats=await api<{tailored_resume:string;cover_letter:string;recruiter_message:string;diff?:string}>(`/applications/${review.id}/materials`,'POST');setPack({...pack,resume:mats.tailored_resume,cover_letter:mats.cover_letter,recruiter_message:mats.recruiter_message,diff:mats.diff});setReview({...review,package:{...review.package,resume:mats.tailored_resume,cover_letter:mats.cover_letter,recruiter_message:mats.recruiter_message,diff:mats.diff}});await refresh();setNotice('Full application suite generated.');})}>{busy==='materials'?'Synthesizing...':'Generate full suite (Resume + Letter + Recruiter message)'}</button>}{showDiff&&pack.diff&&<pre style={{background:'#1e1e24',color:'#f3f4f6',padding:12,borderRadius:8,fontSize:'0.78rem',maxHeight:200,overflow:'auto',fontFamily:'monospace',marginBottom:12}}>{pack.diff}</pre>}{['prepared','approved'].includes(review.status)&&<button className="text-button document-mode" disabled={!!busy} onClick={()=>act('regenerate',async()=>{const a=await api<Application>(`/applications/${review.id}/regenerate`,'POST');setReview(a);setPack(a.package);setEditDocument(false);await refresh();setNotice('Documents regenerated. Review before approval.');})}>{busy==='regenerate'?'Regenerating documents...':'Regenerate from my full resume'}</button>}<button className="text-button document-mode" onClick={()=>setEditDocument(!editDocument)}>{editDocument?'Preview saved document':'Edit document'}</button>{editDocument?<textarea className="document-editor" aria-label={docTab==='resume'?'Edit tailored resume':'Edit cover letter'} value={pack[docTab]} readOnly={!['prepared','approved'].includes(review.status)} onChange={e=>setPack({...pack,[docTab]:e.target.value})}/>:<iframe key={review.updated+docTab} title="Career Ops application document preview" className="career-document" sandbox="" src={`/api/applications/${review.id}/download?kind=${docTab}&format=html`}/>}<div className="review-extra"><div className="info-box"><VerificationChip v={review.job.verification}/><small> Job: {review.job.match.score}% fit · {review.job.verification?.status==='open'?'confirmed still open on LinkedIn just before the documents were written':'not re-checked yet; the page is checked again before applying, and a closed job is never started'}</small></div>{Object.keys(pack.answers||{}).length>0&&<div className="info-box vertical"><b>Screening answers that will be sent</b>{Object.entries(pack.answers).map(([q,a])=><span key={q}>{q}: {a}</span>)}</div>}<ClaimsPanel grounding={review.grounding} confirmed={pack.confirmed_claims||[]} editable={['prepared','approved'].includes(review.status)} onToggle={c=>setPack({...pack,confirmed_claims:(pack.confirmed_claims||[]).includes(c)?(pack.confirmed_claims||[]).filter(x=>x!==c):[...(pack.confirmed_claims||[]),c]})}/>{(review.evidence||['submitted','needs_verification'].includes(review.status))&&<EvidenceBlock id={review.id} verification={review.job.verification} evidence={review.evidence} status={review.status}/>}</div><div className="review-notes"><div>{pack.notes.map((note,i)=><p key={i}>{note}</p>)}</div><ShieldCheck size={17}/><span>Check every claim. Editing a package clears its previous approval.</span></div><div className="review-footer"><Badge status={review.status}/><div>{['prepared','approved'].includes(review.status)&&<><button className="btn secondary" disabled={!!busy} onClick={()=>act('save',async()=>{const a=await api<Application>(`/applications/${review.id}/package`,'PUT',pack);setReview(a);await refresh();setNotice('Draft saved.')} )}>Save draft</button><button className="btn primary" disabled={!!busy||(review.grounding?.ungrounded||[]).some(c=>!(pack.confirmed_claims||[]).includes(c))} onClick={()=>act('approve',async()=>{await api(`/applications/${review.id}/package`,'PUT',pack);await api('/applications/approve','POST',{ids:[review.id]});await refresh();setReview(null);setLiveId(review.id);navigate('Applications');setNotice('Package approved. Press Start application when you are ready.')} )}><Check size={17}/>Save & approve</button></>}</div></div></section></div>}
 </div>;
}
function JobCard({
  job: j,
  onOpen,
  onArchive,
  onDelete,
  onVerify
}: {
  job: Job;
  onOpen: () => void;
  onArchive?: (id: string) => void;
  onDelete?: (id: string) => void;
  onVerify?: (id: string) => void;
}) {
  const isClosed = j.verification?.status === 'closed' || j.verification?.status === 'uncertain';
  const scoreClass = j.match.score >= 80 ? 'good' : j.match.score >= 60 ? 'fair' : '';
  const isEligible = !j.match.blockers?.length && !j.match.unknown?.length && j.match.matched;
  const isReviewNeeded = !j.match.blockers?.length && (j.match.unknown?.length > 0 || !j.match.matched);
  const eligibility = j.match.blockers?.length
    ? 'Not eligible'
    : isEligible
    ? 'Eligible'
    : 'Review needed';

  // Clean source name (strip ' via JobSpy' or internal tokens)
  const cleanSource = (j.source_attribution || j.source || 'Portal')
    .replace(/\s+via\s+JobSpy/i, '')
    .trim();

  // Location display without duplicating Remote
  const locDisplay = j.mode === 'Remote'
    ? 'Remote'
    : (j.location ? j.location.split(',')[0].trim() : 'India');

  const empTypeDisplay = j.mode === 'Remote'
    ? (j.location && j.location.toLowerCase() !== 'remote' ? j.location.split(',')[0].trim() : 'Full-time')
    : (j.mode || 'Full-time');

  return (
    <article className={`job-card ${j.archived ? 'is-archived' : ''} ${isClosed ? 'is-closed' : ''}`} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div>
        {/* Top Header: Logo, Clean Source Pill, Fit Score */}
        <div className="job-card-top" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Logo job={j}/>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.72rem', padding: '3px 8px', borderRadius: 6, background: '#f1f5f9', color: '#475569', fontWeight: 600 }}>
              {cleanSource}
            </span>
            {isClosed ? (
              <span style={{ fontSize: '0.72rem', padding: '3px 8px', borderRadius: 6, background: '#fee2e2', color: '#b91c1c', fontWeight: 600 }}>
                Closed
              </span>
            ) : j.verification?.status === 'active' || j.verification?.status === 'open' ? (
              <span style={{ fontSize: '0.72rem', padding: '3px 8px', borderRadius: 6, background: '#dcfce7', color: '#15803d', fontWeight: 600 }}>
                Active
              </span>
            ) : null}
            {j.archived && (
              <span style={{ fontSize: '0.72rem', padding: '3px 8px', borderRadius: 6, background: '#f1f5f9', color: '#64748b', fontWeight: 600 }}>
                Archived
              </span>
            )}
            <span className={`score ${scoreClass}`} style={{ fontWeight: 700 }}>
              <Sparkles size={12}/>{j.match.score}% fit
            </span>
          </div>
        </div>

        {/* Company Row & Eligibility Pill (Properly separated!) */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: 8 }}>
          <span style={{ fontSize: '0.84rem', fontWeight: 600, color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {j.company}
          </span>
          <span style={{
            fontSize: '0.68rem',
            padding: '2px 8px',
            borderRadius: 9999,
            fontWeight: 650,
            whiteSpace: 'nowrap',
            flexShrink: 0,
            background: j.match.blockers?.length ? '#fef2f2' : isEligible ? '#f0fdf4' : '#fffbeb',
            color: j.match.blockers?.length ? '#dc2626' : isEligible ? '#16a34a' : '#d97706',
            border: `1px solid ${j.match.blockers?.length ? '#fecaca' : isEligible ? '#bbf7d0' : '#fde68a'}`
          }}>
            {eligibility}
          </span>
        </div>

        {/* Job Title Button */}
        <h3 style={{ margin: '0 0 10px', fontSize: '1rem', lineHeight: 1.4 }}>
          <button onClick={onOpen} style={{ textAlign: 'left', fontWeight: 700, color: '#0f172a' }}>
            {j.title}
          </button>
        </h3>

        {/* Job Meta: Location and Employment Type (Never duplicates Remote!) */}
        <div className="job-meta" style={{ display: 'flex', gap: 12, marginBottom: 12, color: '#64748b', fontSize: '0.78rem' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><MapPin size={14}/>{locDisplay}</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><BriefcaseBusiness size={14}/>{empTypeDisplay}</span>
        </div>

        {/* Skill tags */}
        <div className="skill-tags" style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 12 }}>
          {(j.skills || []).slice(0, 3).map(s => <span key={s}>{s}</span>)}
          {(!j.skills || j.skills.length === 0) && <span>{cleanSource}</span>}
        </div>
      </div>

      {/* Footer: Salary/Status on Left, Clean Action Buttons on Right */}
      <div className="job-card-foot" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14, paddingTop: 12, borderTop: '1px solid #f1f5f9' }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#334155' }}>
            {j.salary && j.salary !== 'Competitive' ? j.salary : (j.posted ? `Posted ${j.posted}` : 'Actively hiring')}
          </span>
          <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
            {j.mode || 'Full-time'} &bull; {cleanSource}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
          {onVerify && !isClosed && (
            <button
              type="button"
              className="icon-button"
              style={{ width: 30, height: 30, padding: 0, borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff' }}
              title="Verify if listing is active"
              onClick={e => { e.stopPropagation(); onVerify(j.id); }}
            >
              <RefreshCw size={13}/>
            </button>
          )}
          {j.url && (
            <a
              href={j.url}
              target="_blank"
              rel="noopener noreferrer"
              className="icon-button"
              style={{ width: 30, height: 30, padding: 0, borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
              title="Open original job link"
              onClick={e => e.stopPropagation()}
            >
              <ExternalLink size={13}/>
            </a>
          )}
          {onArchive && (
            <button
              type="button"
              className="icon-button"
              style={{ width: 30, height: 30, padding: 0, borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff' }}
              title={j.archived ? 'Unarchive' : 'Archive'}
              onClick={e => { e.stopPropagation(); onArchive(j.id); }}
            >
              <Archive size={13}/>
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              className="icon-button danger-hover"
              style={{ width: 30, height: 30, padding: 0, borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff', color: '#ef4444' }}
              title="Delete"
              onClick={e => { e.stopPropagation(); onDelete(j.id); }}
            >
              <Trash2 size={13}/>
            </button>
          )}
          <button
            type="button"
            className="btn primary"
            style={{ padding: '4px 10px', fontSize: '0.78rem', height: 30, borderRadius: 8, display: 'inline-flex', alignItems: 'center', gap: 4 }}
            onClick={onOpen}
          >
            Review <ArrowRight size={13}/>
          </button>
        </div>
      </div>
    </article>
  );
}
