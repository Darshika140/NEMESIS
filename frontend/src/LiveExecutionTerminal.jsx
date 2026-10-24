import { useEffect, useRef, useState } from "react";

const logMessages = [
  { text: "> Initializing agent workspace...", tone: "text-zinc-400" },
  { text: "> Generating adversarial scenario 1...", tone: "text-emerald-300" },
  { text: "> Scenario failed. Triggering self-healing...", tone: "text-amber-300" },
  { text: "> Fixer proposed an instruction patch.", tone: "text-zinc-300" },
  { text: "> Red Team stress-testing the updated agent...", tone: "text-emerald-300" },
  { text: "> Fix validated.", tone: "text-emerald-200" },
  { text: "> Generating adversarial scenario 2...", tone: "text-emerald-300" },
  { text: "> Regression checks passed. Continuing pipeline...", tone: "text-zinc-300" },
];

function timestamp() {
  return new Date().toLocaleTimeString([], { hour12: false });
}

export default function LiveExecutionTerminal({ active = false, run }) {
  const [logs, setLogs] = useState([]);
  const nextLogIndex = useRef(1);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    nextLogIndex.current = 1;
    setLogs([{ ...logMessages[0], time: timestamp() }]);
    const interval = window.setInterval(() => {
      const message = logMessages[nextLogIndex.current % logMessages.length];
      nextLogIndex.current += 1;
      setLogs((current) => [
        ...current.slice(-7),
        { ...message, time: timestamp() },
      ]);
    }, 1400);

    return () => window.clearInterval(interval);
  }, [active, run?.id]);

  useEffect(() => {
    if (active) return;
    setLogs(
      run?.status === "completed"
        ? [
            { text: `> Pipeline completed · run ${run.id?.slice(0, 8) ?? "unknown"}`, tone: "text-emerald-300", time: timestamp() },
            { text: `> ${run.metrics?.scenarios_generated ?? 0} scenarios generated · ${run.metrics?.failures_discovered ?? 0} failures detected`, tone: "text-zinc-400", time: timestamp() },
            { text: `> ${run.metrics?.fixes_resolved ?? 0} fixes resolved · verification results loaded`, tone: "text-zinc-400", time: timestamp() },
          ]
        : [],
    );
  }, [active, run?.id, run?.status, run?.metrics?.scenarios_generated, run?.metrics?.failures_discovered, run?.metrics?.fixes_resolved]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [logs]);

  return (
    <section
      aria-label="Pipeline execution log"
      aria-live="polite"
      className="theme-panel h-full overflow-hidden rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09]"
    >
      <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
        <div>
          <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Active terminal</p>
          <h2 className="text-sm font-semibold text-zinc-100">Execution trace</h2>
        </div>
        <div className="flex items-center gap-2 font-mono text-[9px] text-emerald-300">
          <span className="relative flex size-2">
            {active && <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400/60" />}
            <span className={`relative inline-flex size-2 rounded-full ${active ? "bg-emerald-400" : "bg-zinc-600"}`} />
          </span>
          {active ? run?.mode === "local_llm" ? "OLLAMA LOCAL · SIMULATED STREAM" : "GROQ CLOUD · SIMULATED STREAM" : run?.status === "completed" ? run?.mode === "local_llm" ? "OLLAMA LOCAL · COMPLETE" : "GROQ CLOUD · COMPLETE" : "STANDBY"}
        </div>
      </div>
      <div className="theme-terminal-window mx-4 my-4 h-[220px] overflow-y-auto rounded-lg border border-white/[0.07] bg-[#060907] px-4 py-3 font-mono text-[10px] leading-7 sm:mx-5 sm:px-5 sm:text-[11px]">
        <div className="mb-3 flex items-center justify-between border-b border-white/[0.06] pb-3 text-[9px] text-zinc-700">
          <span><span className="mr-1.5 text-rose-400/60">●</span><span className="mr-1.5 text-amber-300/60">●</span><span className="mr-3 text-emerald-300/60">●</span>nemesis — pipeline/verify</span>
          <span>RUN {run?.id?.slice(0, 8)?.toUpperCase() ?? "AWAITING"}</span>
        </div>
        {!active && logs.length === 0 && (
          <p className="py-5 text-zinc-700">No execution trace yet. Start a pipeline run to see orchestration activity.</p>
        )}
        {logs.map((log, index) => (
          <div key={`${log.time}-${index}`} className="flex gap-3">
            <span className="shrink-0 text-zinc-600">[{log.time}]</span>
            <span className={log.tone}>{log.text}</span>
          </div>
        ))}
        {active && <div className="flex gap-3"><span className="text-emerald-400">&gt;</span><span className="h-3 w-1.5 animate-pulse bg-emerald-400" /></div>}
        <div ref={bottomRef} />
      </div>
    </section>
  );
}
