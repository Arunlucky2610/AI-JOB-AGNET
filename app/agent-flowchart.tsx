'use client';

import React from 'react';
import { 
  Search, Sparkles, FileText, HelpCircle, ShieldCheck, CheckCircle2, 
  Check, ArrowRight, Zap, Clock, ShieldAlert
} from 'lucide-react';

interface SimpleStep {
  id: string;
  num: number;
  title: string;
  shortTag: string;
  desc: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  accentColor: string;
  accentBg: string;
}

const STEPS: SimpleStep[] = [
  {
    id: 'discovery',
    num: 1,
    title: 'Find Jobs',
    shortTag: 'Live Discovery',
    desc: 'Searches real openings on Indeed, LinkedIn & Naukri',
    icon: Search,
    accentColor: '#059669',
    accentBg: '#ecfdf5',
  },
  {
    id: 'matching',
    num: 2,
    title: 'Check Fit',
    shortTag: 'DeepSeek AI',
    desc: 'Analyzes JD requirements against your experience',
    icon: Sparkles,
    accentColor: '#7c3aed',
    accentBg: '#f5f3ff',
  },
  {
    id: 'tailoring',
    num: 3,
    title: 'Tailor Resume',
    shortTag: 'Custom Docs',
    desc: 'Generates role-specific resume bullets & cover letter',
    icon: FileText,
    accentColor: '#d97706',
    accentBg: '#fffbeb',
  },
  {
    id: 'memory_fill',
    num: 4,
    title: 'Fill Answers',
    shortTag: 'Question Memory',
    desc: 'Auto-answers screening questions from saved memory',
    icon: HelpCircle,
    accentColor: '#0284c7',
    accentBg: '#f0f9ff',
  },
  {
    id: 'human_gate',
    num: 5,
    title: 'Safety Check',
    shortTag: 'Account Guard',
    desc: 'Pauses for CAPTCHA & auth to keep account safe',
    icon: ShieldCheck,
    accentColor: '#e11d48',
    accentBg: '#fff1f2',
  },
  {
    id: 'submission',
    num: 6,
    title: 'Apply & Proof',
    shortTag: 'Verified Submit',
    desc: 'Submits 1-click apply and saves screenshot receipt',
    icon: CheckCircle2,
    accentColor: '#16a34a',
    accentBg: '#f0fdf4',
  },
];

export function AgentWorkflowFlowchart({ 
  currentPhase, 
  status 
}: { 
  currentPhase?: string; 
  status?: string 
}) {
  // Determine current active step index (0-5)
  const getActiveIndex = () => {
    if (!status || status === 'idle') return 0; // Show first step ready
    if (status === 'completed') return 5;
    if (status === 'needs_input' || status === 'paused') return 4;
    if (currentPhase === 'searching' || currentPhase === 'discovery') return 0;
    if (currentPhase === 'evaluating' || currentPhase === 'ranking') return 1;
    if (currentPhase === 'preparing' || currentPhase === 'tailoring') return 2;
    if (currentPhase === 'applying' || currentPhase === 'filling') return 3;
    if (status === 'submitting' || status === 'submitted') return 5;
    return 0;
  };

  const activeIdx = getActiveIndex();
  const isRunning = status === 'running' || currentPhase === 'searching' || currentPhase === 'applying';
  const progressPercent = status === 'completed' ? 100 : Math.round(((activeIdx + 1) / STEPS.length) * 100);

  return (
    <section className="modern-flow-container">
      {/* Top Banner with Progress & Context */}
      <div className="flow-header-wrapper">
        <div className="flow-title-group">
          <div className="flow-pill-tag">
            <Zap size={13} className="flow-pill-icon" />
            <span>HOW RAPIDSKILL AI WORKS</span>
          </div>
          <h2 className="flow-main-title">6-Step Autonomous Application Pipeline</h2>
          <p className="flow-subtitle">
            What your agent does behind the scenes to discover, verify, tailor, and submit each application.
          </p>
        </div>

        <div className="flow-status-pill-box">
          {status === 'completed' ? (
            <div className="flow-status-badge badge-completed">
              <Check size={15} />
              <span>All 6 Stages Completed</span>
            </div>
          ) : isRunning ? (
            <div className="flow-status-badge badge-active">
              <span className="live-radar-dot" />
              <span>Stage {activeIdx + 1} of 6: <b>{STEPS[activeIdx]?.title}</b></span>
            </div>
          ) : status === 'needs_input' ? (
            <div className="flow-status-badge badge-paused">
              <ShieldAlert size={15} />
              <span>Awaiting Your Checkpoint Input</span>
            </div>
          ) : (
            <div className="flow-status-badge badge-idle">
              <Clock size={14} />
              <span>Ready · Click Start Agent to Begin</span>
            </div>
          )}
        </div>
      </div>

      {/* Progress Bar Line */}
      <div className="flow-progress-track">
        <div 
          className="flow-progress-fill" 
          style={{ width: `${status === 'idle' ? 16 : progressPercent}%` }}
        />
      </div>

      {/* 6 High-Fidelity Cards Grid */}
      <div className="flow-cards-track">
        {STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isDone = activeIdx > idx || status === 'completed';
          const isActive = (activeIdx === idx && status !== 'completed' && status !== 'idle') || (idx === 0 && status === 'idle');
          const isPending = activeIdx < idx && status !== 'completed';

          return (
            <div 
              key={step.id} 
              className={`flow-step-tile ${isActive ? 'tile-active' : ''} ${isDone ? 'tile-done' : ''} ${isPending ? 'tile-pending' : ''}`}
              style={{
                '--step-accent': step.accentColor,
                '--step-bg': step.accentBg,
              } as React.CSSProperties}
            >
              {/* Header inside tile: Number Badge + Status Pill */}
              <div className="tile-top-bar">
                <div className={`tile-num-circle ${isDone ? 'circle-done' : isActive ? 'circle-active' : ''}`}>
                  {isDone ? <Check size={13} strokeWidth={2.8} /> : <span>{step.num}</span>}
                </div>

                <span className={`tile-state-pill ${isDone ? 'state-done' : isActive ? 'state-active' : 'state-pending'}`}>
                  {isDone ? 'Completed' : isActive && isRunning ? 'In Progress' : isActive ? 'Ready' : 'Up Next'}
                </span>
              </div>

              {/* Central Icon with Soft Glow */}
              <div className="tile-icon-bubble">
                <Icon size={20} />
              </div>

              {/* Content */}
              <div className="tile-body">
                <span className="tile-short-tag">{step.shortTag}</span>
                <h3 className="tile-title">{step.title}</h3>
                <p className="tile-description">{step.desc}</p>
              </div>

              {/* Step indicator arrow for all except last */}
              {idx < STEPS.length - 1 && (
                <div className={`tile-connector-arrow ${isDone ? 'connector-done' : ''}`}>
                  <ArrowRight size={14} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
