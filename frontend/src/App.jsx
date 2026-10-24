import { useEffect, useMemo, useState } from "react";
import { getLatestRun, getScenario, startRun } from "./api.js";
import AgentBoardroom from "./AgentBoardroom.jsx";
import AuditTrailViewer from "./AuditTrailViewer.jsx";
import DiagnosticChat from "./DiagnosticChat.jsx";
import HallucinationDiffViewer from "./HallucinationDiffViewer.jsx";
import LiveExecutionTerminal from "./LiveExecutionTerminal.jsx";
import ResilienceToggle from "./ResilienceToggle.jsx";

const metricDefinitions = [
  { key: "scenarios_generated", label: "Scenarios generated", detail: "adversarial inputs", icon: "◈" },
  { key: "failures_discovered", label: "Failures discovered", detail: "detected by checker", icon: "⌁" },
  { key: "false_success_claims", label: "False success claims", detail: "agent reported success", icon: "!", tone: "amber" },
  { key: "scenarios_minimized", label: "Scenarios minimized", detail: "reproducible cases", icon: "⌘" },
  { key: "tests_generated", label: "Tests generated", detail: "regression-ready", icon: "⌗" },
  { key: "fixes_validated", label: "Fixes validated", detail: "against failures", icon: "⌕" },
  { key: "fixes_resolved", label: "Fixes resolved", detail: "targeted failures", icon: "✓", tone: "emerald" },
];

function Icon({ name, className = "size-4" }) {
  const common = {
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };

  const paths = {
    terminal: <><path d="m4 17 6-5-6-5" /><path d="M12 19h8" /></>,
    pulse: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
    branch: <><circle cx="6" cy="6" r="2" /><circle cx="18" cy="18" r="2" /><path d="M8 6h3a4 4 0 0 1 4 4v4a4 4 0 0 0 3 4" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    down: <path d="m7 10 5 5 5-5" />,
    arrow: <><path d="M7 17 17 7" /><path d="M7 7h10v10" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  };

  return <svg {...common}>{paths[name] ?? null}</svg>;
}

function BrandMark() {
  return (
    <div className="flex size-9 items-center justify-center rounded-xl border border-emerald-300/20 bg-emerald-300/[0.08] text-emerald-300 shadow-[0_0_22px_rgba(52,211,153,0.16)]">
      <svg className="size-6" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path d="M4 24.5 11.2 8.8a2.3 2.3 0 0 1 4.1-.1l3 6.1 2.8-4.7a2.3 2.3 0 0 1 4 .1l3 5.6-3.6 7.9-4.1-7.2-3.1 5.1a2.3 2.3 0 0 1-4 .1l-2.8-5.4-4.1 8.9H4Z" fill="currentColor" />
      </svg>
    </div>
  );
}

const executionStages = ["Generating Scenarios...", "Testing...", "Applying Fixes..."];

function Header({ run, onRun, runPending, pipelineRunning, executionStage, provider, onProviderChange, theme, onThemeToggle }) {
  const status = run?.status ?? "no runs yet";
  const statusTone =
    pipelineRunning
      ? "text-amber-300"
      : status === "completed"
      ? "text-emerald-300"
      : status === "failed"
        ? "text-rose-300"
        : "text-amber-300";
  return (
    <header className="dashboard-header sticky top-0 z-30 border-b border-white/[0.08] bg-[#050806]/90 backdrop-blur-2xl">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-5 py-3.5 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <BrandMark />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold tracking-[0.14em] text-zinc-100">NEMESIS</span>
              <span className="hidden h-4 w-px bg-white/10 sm:inline" />
              <span className="hidden font-mono text-[9px] tracking-[0.2em] text-zinc-600 sm:inline">AI RELIABILITY</span>
            </div>
            <p className="truncate text-[10px] text-zinc-600">Agent integrity console</p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <div className="hidden shrink-0 items-center gap-2.5 whitespace-nowrap rounded-full border border-emerald-400/20 bg-emerald-400/[0.045] px-3.5 py-2 sm:flex">
            <span className="relative flex size-2">
              <span className={`relative inline-flex size-2 rounded-full shadow-[0_0_10px_currentColor] ${pipelineRunning ? "animate-pulse bg-emerald-300 text-emerald-300" : status === "failed" ? "bg-rose-400 text-rose-400" : "bg-emerald-400 text-emerald-400"}`} />
            </span>
            <span className={`whitespace-nowrap font-mono text-[10px] font-semibold sm:text-[11px] ${pipelineRunning ? "text-emerald-300" : statusTone}`}>{pipelineRunning ? executionStage : status === "completed" ? run?.mode === "local_llm" ? "Pipeline Complete · Local" : "Pipeline Complete" : status === "no runs yet" ? "Pipeline Idle" : status === "failed" ? "Pipeline Error" : `Pipeline ${status}`}</span>
          </div>
          <button
            type="button"
            onClick={onRun}
            disabled={pipelineRunning}
            aria-label="Run pipeline"
            className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-emerald-200/30 bg-gradient-to-b from-emerald-300 to-emerald-500 px-3.5 py-2.5 text-xs font-bold text-[#03110a] shadow-[0_0_24px_rgba(16,185,129,0.22)] transition-all duration-300 hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-emerald-200/60 disabled:cursor-not-allowed disabled:opacity-50 sm:px-4"
          >
            {pipelineRunning ? (
              <svg className="size-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-90" fill="currentColor" d="M12 3a9 9 0 0 1 9 9h-3a6 6 0 0 0-6-6V3Z" />
              </svg>
            ) : <Icon name="pulse" />}
            <span>{pipelineRunning ? "Executing..." : "Run Pipeline"}</span>
          </button>
          <button
            type="button"
            onClick={onThemeToggle}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            aria-pressed={theme === "light"}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.035] text-zinc-400 transition hover:border-emerald-300/25 hover:text-emerald-300 focus:outline-none focus:ring-2 focus:ring-emerald-300/40"
          >
            {theme === "dark" ? (
              <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
              </svg>
            ) : (
              <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M20.9 13A8.5 8.5 0 0 1 11 3.1 8.5 8.5 0 1 0 20.9 13Z" />
              </svg>
            )}
          </button>
          <div className="hidden shrink-0 sm:block">
            <ResilienceToggle provider={provider} onChange={onProviderChange} />
          </div>
        </div>
      </div>
      <div className="flex justify-center border-t border-white/[0.04] px-4 py-2 sm:hidden">
        <ResilienceToggle provider={provider} onChange={onProviderChange} />
      </div>
      <div className="flex items-center justify-center gap-2 border-t border-white/[0.04] bg-white/[0.015] px-4 py-2 text-[10px] sm:hidden">
        <span className={`size-1.5 rounded-full ${pipelineRunning ? "animate-pulse bg-emerald-300" : status === "failed" ? "bg-rose-400" : "bg-emerald-400"}`} />
        <span className={`font-medium ${statusTone}`}>{pipelineRunning ? executionStage : status === "completed" ? run?.mode === "local_llm" ? "Pipeline Complete · Local" : "Pipeline Complete" : `Status: ${status}`}</span>
      </div>
    </header>
  );
}

function SectionHeading({ eyebrow, title, detail, action }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="mb-1.5 font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">{eyebrow}</p>
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h2 className="text-base font-semibold tracking-tight text-slate-100">{title}</h2>
          {detail && <span className="text-xs text-zinc-500">{detail}</span>}
        </div>
      </div>
      {action}
    </div>
  );
}

function MetricCard({ metric, index }) {
  const tone = metric.tone;

  return (
    <article
      className={`theme-metric-card ${tone === "amber" ? "theme-metric-warning" : ""} group relative min-h-48 overflow-hidden rounded-xl border bg-gradient-to-br from-[#0d120f] to-[#090c0a] p-6 transition-all duration-300 hover:-translate-y-0.5 hover:bg-[#101612] ${tone === "amber" ? "border-amber-400/20 hover:border-amber-300/35" : tone === "emerald" ? "border-emerald-400/20 hover:border-emerald-300/35" : "border-white/[0.09] hover:border-white/[0.17]"}`}
      style={{ animationDelay: `${index * 45}ms` }}
    >
      <div aria-hidden="true" className={`pointer-events-none absolute inset-x-0 bottom-0 h-16 opacity-50 blur-2xl ${tone === "amber" ? "bg-amber-400/10" : tone === "emerald" ? "bg-emerald-400/10" : "bg-white/[0.025]"}`} />
      <div className="relative mb-8 flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-zinc-400">{metric.label}</span>
        <Icon name="arrow" className="size-3.5 text-zinc-700 transition-colors group-hover:text-zinc-400" />
      </div>
      <div className={`relative font-mono text-4xl font-medium tracking-tight ${tone === "amber" ? "text-amber-100" : tone === "emerald" ? "text-emerald-100" : "text-zinc-100"}`}>{metric.value}</div>
      <p className="relative mt-3 text-[10px] text-zinc-600">{metric.detail}</p>
    </article>
  );
}

function MetricsOverview({ run, loading }) {
  const values = run?.metrics ?? {};
  return (
    <section aria-labelledby="metrics-title">
      <SectionHeading
        eyebrow={`Run overview / ${run?.created_at ? new Date(run.created_at).toLocaleString() : "waiting for first run"}`}
        title="Pipeline summary"
        detail={run ? `booking · ${run.id.slice(0, 8)}` : "booking · no run id"}
        action={
          <button type="button" className="inline-flex items-center gap-1.5 text-[11px] text-slate-500 transition hover:text-slate-300">
            <Icon name="clock" className="size-3.5" />
            Run history
            <Icon name="chevron" className="size-3" />
          </button>
        }
      />
      <h2 id="metrics-title" className="sr-only">Pipeline metrics</h2>
      {loading ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4" aria-label="Loading pipeline metrics">
          {metricDefinitions.map((metric) => (
            <div key={metric.key} className="h-36 animate-pulse rounded-xl border border-white/10 bg-zinc-900/40 p-6 backdrop-blur-md">
            <div className="h-3 w-2/3 rounded bg-zinc-800/50" />
            <div className="mt-7 h-8 w-1/3 rounded bg-zinc-800/50" />
            <div className="mt-3 h-2 w-1/2 rounded bg-zinc-800/40" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
          {metricDefinitions.map((definition, index) => (
            <MetricCard
              key={definition.key}
              metric={{ ...definition, value: String(values[definition.key] ?? 0) }}
              index={index}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function StatusPill({ tone, children }) {
  const styles =
    tone === "red"
      ? "border-rose-400/20 bg-rose-400/[0.08] text-rose-300"
      : "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-300";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-medium ${styles}`}>
      <span className={`size-1.5 rounded-full ${tone === "red" ? "bg-rose-400" : "bg-emerald-400"}`} />
      {children}
    </span>
  );
}

function AgentPanel({ variant, title, subtitle, status, testName, output, duration }) {
  const fixed = variant === "fixed";
  return (
    <article
      className={`theme-panel overflow-hidden rounded-xl border ${
        fixed ? "border-emerald-400/15 bg-zinc-900/50 backdrop-blur-md" : "border-rose-400/15 bg-zinc-900/50 backdrop-blur-md"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3.5 sm:px-5">
        <div className="flex items-center gap-3">
          <span
            className={`flex size-8 items-center justify-center rounded-lg border font-mono text-xs ${
              fixed
                ? "border-emerald-400/15 bg-emerald-400/[0.07] text-emerald-300"
                : "border-rose-400/15 bg-rose-400/[0.07] text-rose-300"
            }`}
          >
            {fixed ? <Icon name="check" /> : "×"}
          </span>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
            <p className="font-mono text-[10px] text-slate-600">{subtitle}</p>
          </div>
        </div>
        <StatusPill tone={fixed ? "green" : "red"}>{status}</StatusPill>
      </div>

      <div className="space-y-4 p-4 sm:p-5">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-slate-600">Regression test</span>
          <span className={`rounded px-2 py-1 font-mono text-[10px] ${fixed ? "bg-emerald-400/[0.07] text-emerald-300/80" : "bg-rose-400/[0.07] text-rose-300/80"}`}>
            {testName}
          </span>
        </div>
        <div className={`rounded-lg border p-3.5 ${fixed ? "border-emerald-400/10 bg-[#090e0d]" : "border-rose-400/10 bg-[#100c0d]"}`}>
          <div className="mb-2 flex items-center gap-2 font-mono text-[10px] text-slate-600">
            <span className={fixed ? "text-emerald-400" : "text-rose-400"}>{fixed ? "PASS" : "FAIL"}</span>
            <span>·</span>
            <span>{fixed ? "expected behavior" : "assertion mismatch"}</span>
          </div>
          <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-300">{output || "No agent output recorded."}</p>
        </div>
        <div className="flex items-center justify-between font-mono text-[10px] text-slate-600">
          <span>booking · {fixed ? "booking_v2" : "booking_v1"}</span>
          {duration && <span>{duration}</span>}
        </div>
      </div>
    </article>
  );
}

function AgentComparison({ scenario, loading, provider }) {
  const original = scenario?.verification?.original;
  const fixed = scenario?.verification?.fixed;
  return (
    <section className="theme-section" aria-labelledby="verification-title">
      <SectionHeading
        eyebrow="Self-healing / verification"
        title="Agent comparison"
        detail="same scenario · same regression test"
        action={
          <span className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.07] bg-white/[0.025] px-2.5 py-1.5 font-mono text-[10px] text-slate-500">
            <Icon name="branch" className="size-3.5" />
            {scenario?.scenario ?? "select a failure"}
          </span>
        }
      />
      <h2 id="verification-title" className="sr-only">Side-by-side agent verification</h2>
      <div className="grid gap-3 lg:grid-cols-2">
        {loading ? (
          <div className="lg:col-span-2 rounded-xl border border-white/10 bg-zinc-900/40 p-6 text-sm text-zinc-500 backdrop-blur-md">Loading agent verification…</div>
        ) : scenario ? (
          <>
            <AgentPanel
              variant="original"
              title="Original Agent"
              subtitle="booking_v1 · baseline"
              status={original?.passed ? "Test passed" : "Failure reproduced"}
              testName={scenario.regression_test ?? "Generated regression case"}
              output={original?.final_output}
            />
            <AgentPanel
              variant="fixed"
              title="Fixed Agent"
              subtitle={`booking_v2 · verified · ${provider === "ollama" ? "local" : "Groq"}`}
              status={fixed?.passed === true ? "Test passing" : fixed?.passed === false ? "Unresolved" : "Not validated"}
              testName={scenario.regression_test ?? "Generated regression case"}
              output={fixed?.final_output}
            />
          </>
        ) : (
          <div className="lg:col-span-2 rounded-xl border border-white/10 bg-zinc-900/40 p-6 text-sm text-zinc-500 backdrop-blur-md">
            Run the pipeline or select a discovered failure to load before-and-after verification.
          </div>
        )}
      </div>
    </section>
  );
}

function TraceStep({ step, last }) {
  const tone =
    step.tone === "red"
      ? "text-rose-300"
      : step.tone === "amber"
        ? "text-amber-300"
        : "text-slate-400";
  const dot =
    step.tone === "red"
      ? "bg-rose-400 ring-rose-400/10"
      : step.tone === "amber"
        ? "bg-amber-300 ring-amber-300/10"
        : "bg-slate-600 ring-slate-600/10";

  return (
    <div className="relative grid grid-cols-[16px_74px_minmax(0,1fr)] gap-2.5 pb-4 font-mono text-[10px] sm:grid-cols-[16px_88px_minmax(0,1fr)]">
      {!last && <span className="absolute bottom-0 left-[6px] top-2 w-px bg-white/[0.07]" />}
      <span className={`relative z-10 mt-0.5 size-3 rounded-full ring-4 ${dot}`} />
      <span className="text-slate-600">{step.time}</span>
      <div className="min-w-0">
        <span className="text-slate-300">{step.label}</span>
        <span className="mx-2 text-slate-700">→</span>
        <span className={tone}>{step.result}</span>
      </div>
    </div>
  );
}

function FailureRow({ failure, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-full rounded-lg border px-3.5 py-3 text-left transition ${
        selected
          ? "border-emerald-300/20 bg-emerald-300/[0.045]"
          : "border-transparent bg-[#0d1014] hover:border-white/[0.08] hover:bg-[#11151a]"
      }`}
    >
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md font-mono text-[10px] ${
          failure.kind === "false_success_claim"
            ? "bg-amber-400/[0.09] text-amber-300"
            : "bg-rose-400/[0.08] text-rose-300"
        }`}>
          !
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs font-medium text-slate-200">{failure.title}</span>
            <span className="font-mono text-[9px] text-slate-600">{failure.id}</span>
          </span>
          <span className="mt-1 block truncate font-mono text-[10px] text-slate-600">{failure.scenario}</span>
        </span>
        <span className="hidden shrink-0 items-center gap-1 rounded-full border border-emerald-400/10 px-2 py-0.5 font-mono text-[9px] text-emerald-400/80 sm:inline-flex">
          <Icon name="check" className="size-3" />
          {failure.status}
        </span>
        <Icon name="chevron" className={`mt-1 size-3.5 shrink-0 transition ${selected ? "rotate-90 text-emerald-300" : "text-slate-600"}`} />
      </div>
    </button>
  );
}

function TraceDetail({ failure }) {
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-white/[0.07] bg-[#0c0f13]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] px-4 py-3">
        <div>
          <p className="text-xs font-medium text-slate-200">{failure.title}</p>
          <p className="mt-1 font-mono text-[9px] text-slate-600">{failure.kind} · {failure.scenario}</p>
        </div>
        <button
          type="button"
          aria-label="Copy failure identifier"
          onClick={() => navigator.clipboard?.writeText(failure.id)}
          className="inline-flex items-center gap-1.5 rounded border border-white/[0.07] px-2 py-1 font-mono text-[9px] text-slate-500 transition hover:text-slate-300"
        >
          <Icon name="copy" className="size-3" />
          {failure.id}
        </button>
      </div>
      <div className="p-4 sm:p-5">
        <p className="mb-4 text-xs leading-relaxed text-slate-400">{failure.summary}</p>
        <div className="mb-4">
          {failure.steps.map((step, index) => (
            <TraceStep key={`${step.time}-${step.label}`} step={step} last={index === failure.steps.length - 1} />
          ))}
        </div>
        <div className="rounded-md border border-amber-300/10 bg-amber-300/[0.035] p-3.5">
          <p className="mb-1.5 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.14em] text-amber-300/80">
            <span className="text-amber-300">∴</span>
            Failure mechanism
          </p>
          <p className="font-mono text-[10px] leading-relaxed text-slate-400">{failure.mechanism}</p>
        </div>
      </div>
    </div>
  );
}

function TraceViewer({ failures, selectedId, onSelect, selectedFailure, loading }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <section aria-labelledby="trace-title" className="pb-10">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Observability / execution trace</p>
          <button
            type="button"
            id="trace-title"
            aria-expanded={expanded}
            onClick={() => setExpanded((current) => !current)}
            className="group flex items-center gap-2 text-left"
          >
            <h2 className="text-base font-semibold tracking-tight text-slate-100">Hallucination trace</h2>
            <Icon name="down" className={`size-4 text-slate-500 transition group-hover:text-slate-300 ${expanded ? "" : "-rotate-90"}`} />
          </button>
          <p className="mt-1 text-xs text-slate-500">Inspect the logic behind each discovered failure.</p>
        </div>
        <div className="flex items-center gap-2 font-mono text-[10px] text-slate-500">
          <span className="size-1.5 rounded-full bg-amber-300" />
          {failures.length} failures
          <span className="text-slate-700">·</span>
          <span>{failures.filter((failure) => failure.status === "Resolved").length} resolved</span>
        </div>
      </div>

      {expanded && (
        <div className="theme-panel rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09] p-3 sm:p-4">
          <div className="mb-3 flex items-center justify-between px-1">
            <span className="font-mono text-[10px] uppercase tracking-wider text-slate-600">Failure index</span>
            <span className="font-mono text-[9px] text-slate-700">select an event to inspect</span>
          </div>
          {failures.length === 0 ? (
            <p className="rounded-lg border border-dashed border-white/[0.08] px-4 py-8 text-center text-xs text-slate-600">
              No failed scenarios are available for this run.
            </p>
          ) : (
            <>
              <div className="space-y-1.5">
                {failures.map((failure) => (
                  <FailureRow
                    key={failure.id}
                    failure={failure}
                    selected={failure.id === selectedId}
                    onSelect={() => onSelect(failure.id)}
                  />
                ))}
              </div>
              {loading ? (
                <div className="mt-3 animate-pulse rounded-lg border border-white/[0.07] bg-[#0c0f13] p-6 text-xs text-slate-600">Loading trace details…</div>
              ) : selectedFailure ? (
                <TraceDetail failure={selectedFailure} />
              ) : null}
            </>
          )}
        </div>
      )}
    </section>
  );
}

function ThreatSignals({ failures, selectedId, onSelect }) {
  const recent = failures.slice(0, 4);
  return (
    <section className="theme-panel overflow-hidden rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09]" aria-labelledby="threat-signals-title">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
        <div>
          <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Threat signals</p>
          <h2 id="threat-signals-title" className="text-sm font-semibold text-zinc-100">Recent detections</h2>
        </div>
        <span className="font-mono text-[10px] text-zinc-600">{failures.length} total</span>
      </div>
      {recent.length === 0 ? (
        <div className="px-5 py-8 text-center">
          <span className="mx-auto mb-3 flex size-9 items-center justify-center rounded-full border border-emerald-400/15 bg-emerald-400/[0.06] text-emerald-300">✓</span>
          <p className="text-xs font-medium text-zinc-300">No detections in this run</p>
          <p className="mt-1 text-[10px] text-zinc-600">Failures will appear here as the pipeline reports them.</p>
        </div>
      ) : (
        <div className="px-5">
          {recent.map((failure) => {
            const selected = failure.id === selectedId;
            const isClaim = failure.kind === "false_success_claim";
            return (
              <button
                key={failure.id}
                type="button"
                onClick={() => onSelect(failure.id)}
                className={`flex w-full items-center gap-3 border-b border-white/[0.06] py-4 text-left transition last:border-b-0 ${selected ? "bg-emerald-400/[0.025]" : "hover:bg-white/[0.015]"}`}
                aria-pressed={selected}
              >
                <span className={`flex size-8 shrink-0 items-center justify-center rounded-lg font-mono text-xs ${isClaim ? "bg-amber-400/[0.08] text-amber-300" : "bg-rose-400/[0.08] text-rose-300"}`}>{isClaim ? "!" : "×"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold text-zinc-200">{failure.title}</span>
                  <span className="mt-1 block truncate font-mono text-[9px] text-zinc-600">{failure.scenario} · {failure.id.slice(0, 8)}</span>
                </span>
                <span className={`font-mono text-[9px] uppercase ${failure.status === "Resolved" ? "text-emerald-400" : "text-rose-300"}`}>{failure.status === "Resolved" ? "Fixed" : "Open"}</span>
              </button>
            );
          })}
        </div>
      )}
      <div className="mx-5 mb-5 rounded-lg border border-white/[0.07] bg-black/20 p-4">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-zinc-500">Fixes resolved</span>
          <span className="font-mono text-sm font-semibold text-emerald-300">{failures.filter((failure) => failure.status === "Resolved").length}<span className="ml-1 text-[9px] font-normal text-zinc-600">/ {failures.length}</span></span>
        </div>
        <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/[0.06]">
          <div className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-300 transition-all" style={{ width: `${failures.length ? (failures.filter((failure) => failure.status === "Resolved").length / failures.length) * 100 : 0}%` }} />
        </div>
        <p className="mt-2 font-mono text-[9px] text-zinc-700">Based on detected failures in the current run</p>
      </div>
    </section>
  );
}

function Footer({ runId }) {
  return (
    <footer className="border-t border-white/[0.06]">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-2 px-5 py-4 font-mono text-[9px] text-slate-700 sm:px-8">
        <span>NEMESIS // AGENT RELIABILITY SYSTEM</span>
        <span className="flex items-center gap-2">
          <span>{runId ?? "no-run"}</span>
          <span className="text-slate-800">·</span>
          <span>build 0.1.0</span>
        </span>
      </div>
    </footer>
  );
}

export default function App() {
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshError, setRefreshError] = useState("");
  const [runError, setRunError] = useState("");
  const [runPending, setRunPending] = useState(false);
  const [executionStageIndex, setExecutionStageIndex] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedFailure, setSelectedFailure] = useState(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [theme, setTheme] = useState(() => window.localStorage.getItem("nemesis-theme") ?? "dark");
  const [provider, setProvider] = useState(
    () => window.localStorage.getItem("nemesis-inference-provider") ?? "groq",
  );
  const failures = run?.failures ?? [];
  const pipelineRunning = runPending || ["queued", "running"].includes(run?.status);
  const executionStage = executionStages[executionStageIndex];

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("nemesis-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!pipelineRunning) {
      setExecutionStageIndex(0);
      return undefined;
    }

    const interval = window.setInterval(() => {
      setExecutionStageIndex((current) => (current + 1) % executionStages.length);
    }, 2400);
    return () => window.clearInterval(interval);
  }, [pipelineRunning]);

  useEffect(() => {
    const controller = new AbortController();
    let timer;

    async function refresh() {
      try {
        const latest = await getLatestRun(controller.signal);
        setRun(latest);
        setRefreshError("");
        if (latest && ["queued", "running"].includes(latest.status)) {
          timer = setTimeout(refresh, 2000);
        } else {
          setLoading(false);
        }
      } catch (error) {
        if (error.name !== "AbortError") {
          setRefreshError(error.message);
          setLoading(false);
        }
      }
    }

    refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!failures.some((failure) => failure.id === selectedId)) {
      setSelectedId(failures[0]?.id ?? null);
      setSelectedFailure(null);
    }
  }, [run?.id, failures, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedFailure(null);
      setScenarioLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setScenarioLoading(true);
    setSelectedFailure(null);
    getScenario(selectedId, controller.signal)
      .then(setSelectedFailure)
      .catch((error) => {
        if (error.name !== "AbortError") setRunError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setScenarioLoading(false);
      });
    return () => controller.abort();
  }, [selectedId]);

  async function refreshLatest() {
    const latest = await getLatestRun();
    setRun(latest);
    return latest;
  }

  async function handleRun() {
    setRunPending(true);
    setRunError("");
    try {
      const accepted = await startRun({
        mode: provider === "ollama" ? "local_llm" : "live_llm",
        nScenarios: 4,
      });
      setRun(accepted);
      setLoading(true);
      const latest = await refreshLatest();
      if (latest && ["queued", "running"].includes(latest.status)) {
        setTimeout(async function poll() {
          try {
            const next = await refreshLatest();
            if (next && ["queued", "running"].includes(next.status)) {
              setTimeout(poll, 2000);
            } else {
              setLoading(false);
            }
          } catch (error) {
            setRunError(error.message);
            setLoading(false);
          }
        }, 1000);
      } else {
        setLoading(false);
      }
    } catch (error) {
      setRunError(error.message);
    } finally {
      setRunPending(false);
    }
  }

  const matchingScenario =
    selectedFailure?.id === selectedId ? selectedFailure : null;
  const executionLogs = {
    run,
    selected_scenario: matchingScenario,
  };

  function changeProvider(nextProvider) {
    setProvider(nextProvider);
    window.localStorage.setItem("nemesis-inference-provider", nextProvider);
  }

  function toggleTheme() {
    setTheme((current) => current === "dark" ? "light" : "dark");
  }

  return (
    <div className="dashboard-root relative min-h-screen overflow-hidden bg-[#050806] text-zinc-100 selection:bg-emerald-300/20">
      <div
        aria-hidden="true"
        className="dashboard-grid pointer-events-none fixed inset-0 bg-[linear-gradient(rgba(45,65,53,0.10)_1px,transparent_1px),linear-gradient(90deg,rgba(45,65,53,0.10)_1px,transparent_1px),radial-gradient(ellipse_at_top,_rgba(16,185,129,0.08),_transparent_52%)] bg-[size:80px_80px,80px_80px,100%_100%]"
      />
      <div className="relative z-10">
      <Header
        run={run}
        onRun={handleRun}
        runPending={runPending}
        pipelineRunning={pipelineRunning}
        executionStage={executionStage}
        provider={provider}
        onProviderChange={changeProvider}
        theme={theme}
        onThemeToggle={toggleTheme}
      />
      <main className="mx-auto max-w-[1600px] px-5 pb-14 pt-10 sm:px-8 sm:pt-14 lg:pt-16">
        <div className="mb-9 flex flex-wrap items-end justify-between gap-5">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.22em] text-emerald-300">
              <span>Overview</span><span className="text-zinc-700">/</span><span>Production</span>
            </div>
            <h1 className="text-4xl font-semibold tracking-[-0.045em] text-zinc-100 sm:text-5xl lg:text-[58px]">System integrity</h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-500 sm:text-base">
              Monitor, trace, and resolve unreliable AI behavior in real time.
            </p>
          </div>
          <div className="mb-1 flex items-center gap-3 rounded-lg border border-white/[0.09] bg-[#0a0f0c] px-4 py-3 font-mono text-[10px]">
            <span className={`size-2 rounded-full shadow-[0_0_10px_currentColor] ${refreshError || run?.status === "failed" ? "bg-rose-400 text-rose-400" : "bg-emerald-400 text-emerald-400"}`} />
            <span className={refreshError || run?.status === "failed" ? "text-rose-300" : "text-emerald-200"}>{refreshError || run?.status === "failed" ? "Pipeline needs attention" : "All systems operational"}</span>
            <span className="hidden text-zinc-700 sm:inline">Updated {run?.created_at ? new Date(run.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "just now"}</span>
          </div>
        </div>

        {(refreshError || runError || (run?.status === "failed" && run.error)) && (
          <div role="alert" className="mb-6 rounded-lg border border-rose-400/15 bg-rose-400/[0.05] px-4 py-3 text-xs text-rose-300">
            {runError || refreshError || run.error}
          </div>
        )}

        <div className="space-y-8">
          <MetricsOverview run={run} loading={loading || pipelineRunning} />
          <div className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
            <LiveExecutionTerminal active={pipelineRunning} run={run} />
            <ThreatSignals failures={failures} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
          <div className="grid gap-8 xl:grid-cols-2">
            <AgentComparison scenario={selectedFailure} loading={scenarioLoading} provider={provider} />
            <TraceViewer
              failures={failures}
              selectedId={selectedId}
              onSelect={setSelectedId}
              selectedFailure={matchingScenario}
              loading={scenarioLoading}
            />
          </div>
          <HallucinationDiffViewer scenario={selectedFailure} />
          <AuditTrailViewer scenario={selectedFailure} />
          <div className="grid gap-4 xl:grid-cols-2">
            <AgentBoardroom scenario={selectedFailure} provider={provider} />
            <DiagnosticChat executionLogs={executionLogs} provider={provider} />
          </div>
        </div>
      </main>
      <Footer runId={run?.id?.slice(0, 8)} />
      </div>
    </div>
  );
}
