import { useEffect, useRef, useState } from "react";
import { sendDiagnosticMessage } from "./api.js";

export default function DiagnosticChat({ executionLogs, provider }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef(null);
  const selectedScenario = executionLogs?.selected_scenario;
  const latestEvidence = [...messages].reverse().find((message) => message.role === "assistant" && message.evidence?.length)?.evidence ?? [];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  async function submit(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || pending) return;

    setDraft("");
    setError("");
    setMessages((current) => [...current, { role: "user", content: message }]);
    setPending(true);
    try {
      const response = await sendDiagnosticMessage({
        message,
        executionLogs,
        provider,
      });
      setMessages((current) => [
        ...current,
        { role: "assistant", content: response.answer, evidence: response.evidence },
      ]);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="theme-panel overflow-hidden rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09]" aria-labelledby="diagnostic-chat-title">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
        <div>
          <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Evidence intelligence</p>
          <h2 id="diagnostic-chat-title" className="text-sm font-semibold text-slate-100">Diagnostic assistant</h2>
        </div>
        <span className={`rounded-full border px-2.5 py-1 font-mono text-[9px] ${provider === "ollama" ? "border-emerald-400/20 bg-emerald-400/[0.04] text-emerald-300" : "border-emerald-400/20 bg-emerald-400/[0.04] text-emerald-300"}`}>
          {provider === "ollama" ? "LOCAL" : "GROQ"}
        </span>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1fr)_250px]">
      <div className="min-w-0">
      <div className="flex flex-wrap gap-2 border-b border-white/[0.06] px-4 py-3">
        {["Explain the root cause", "Show supporting evidence", "How was this fixed?"].map((prompt) => (
          <button key={prompt} type="button" onClick={() => setDraft(prompt)} className="rounded-md border border-white/[0.08] px-2.5 py-1.5 font-mono text-[9px] text-zinc-500 transition hover:border-emerald-400/20 hover:text-emerald-300">{prompt} ↗</button>
        ))}
      </div>
      <div className="flex items-center gap-2 border-b border-white/[0.06] px-4 py-2.5 font-mono text-[9px]">
        <span className="rounded border border-emerald-400/15 bg-emerald-400/[0.04] px-2 py-1 text-emerald-300">ACTIVE CONTEXT</span>
        <span className="truncate text-zinc-600">{selectedScenario?.id ?? executionLogs?.run?.id?.slice(0, 8) ?? "waiting for run evidence"}</span>
      </div>
      <div className="h-64 space-y-3 overflow-y-auto p-4 sm:h-72" aria-live="polite">
        {messages.length === 0 && (
          <div className="rounded-lg border border-dashed border-white/[0.08] p-4">
            <p className="font-mono text-[10px] text-emerald-300">NEMESIS <span className="ml-2 text-zinc-600">NOW</span></p>
            <p className="mt-2 text-xs leading-relaxed text-slate-500">
              Ask about the current run. Answers are grounded only in the JSON execution logs sent with your message.
            </p>
          </div>
        )}
        {messages.map((item, index) => (
          <article key={`${item.role}-${index}`} className={`rounded-lg border p-3 ${item.role === "user" ? "ml-6 border-white/[0.06] bg-white/[0.025]" : "mr-3 border-emerald-300/10 bg-emerald-300/[0.02]"}`}>
            <p className={`mb-1 font-mono text-[9px] uppercase tracking-wider ${item.role === "user" ? "text-slate-600" : "text-emerald-300/80"}`}>
              {item.role === "user" ? "you" : "nemesis assistant"}
            </p>
            <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-300">{item.content}</p>
            {item.evidence?.map((evidence, evidenceIndex) => (
              <div key={`${evidence.path}-${evidenceIndex}`} className="mt-2 border-l border-emerald-300/30 pl-2 font-mono text-[9px] text-slate-500">
                <span className="text-emerald-200/70">{evidence.path}</span>
                <p className="mt-0.5 break-words">{evidence.quote}</p>
              </div>
            ))}
          </article>
        ))}
        {pending && (
          <div className="mr-10 rounded-lg border border-emerald-300/10 bg-emerald-300/[0.025] p-3" role="status" aria-label="Assistant is thinking">
            <div className="mb-2 h-2 w-24 animate-pulse rounded bg-emerald-300/10" />
            <div className="h-2 w-3/4 animate-pulse rounded bg-white/[0.06]" />
            <div className="mt-2 h-2 w-1/2 animate-pulse rounded bg-white/[0.04]" />
          </div>
        )}
        <div ref={endRef} />
      </div>
      {error && <p className="mx-4 mb-2 rounded border border-rose-400/10 bg-rose-400/[0.04] px-2.5 py-2 text-[10px] text-rose-300" role="alert">{error}</p>}
      <form onSubmit={submit} className="mx-4 mb-2 flex items-center gap-2 rounded-lg border border-emerald-400/15 bg-[#080c09] p-2.5 focus-within:border-emerald-400/30">
        <label className="sr-only" htmlFor="diagnostic-message">Ask a diagnostic question</label>
        <span className="pl-1 font-mono text-sm text-emerald-400">›</span>
        <input
          id="diagnostic-message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={8000}
          placeholder="Ask about a failure in this run…"
          className="min-w-0 flex-1 bg-transparent px-1 py-2 font-mono text-[11px] text-slate-200 outline-none placeholder:text-slate-700"
        />
        <button
          type="submit"
          disabled={pending || !draft.trim()}
          className="rounded-md bg-emerald-400 px-3 py-2 text-[10px] font-semibold text-[#04110a] transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Ask
        </button>
      </form>
      <p className="px-4 pb-3 font-mono text-[9px] text-slate-700">Responses are grounded only in the current run’s execution evidence.</p>
      </div>
      <aside className="border-t border-white/[0.06] bg-black/10 p-4 lg:border-l lg:border-t-0 lg:p-5">
        <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-600">Run evidence</p>
        <div className="my-4 flex items-center gap-3">
          <div className="flex size-14 items-center justify-center rounded-full border-[3px] border-emerald-400/70 font-mono text-[10px] font-semibold text-emerald-300 shadow-[0_0_18px_rgba(52,211,153,0.1)]">
            {latestEvidence.length ? `${latestEvidence.length}` : "—"}
          </div>
          <div><p className="text-[11px] font-medium text-zinc-300">{latestEvidence.length ? "Cited sources" : "No citations yet"}</p><p className="mt-1 text-[9px] text-zinc-600">Evidence in latest answer</p></div>
        </div>
        <div className="space-y-2 border-t border-white/[0.06] pt-3">
          {(latestEvidence.length ? latestEvidence : [
            { path: "run.status", quote: executionLogs?.run?.status ?? "waiting" },
            { path: "scenario", quote: selectedScenario?.scenario ?? "No scenario selected" },
            { path: "verification", quote: selectedScenario ? `original: ${selectedScenario.verification?.original?.passed ? "pass" : "fail"} · fixed: ${selectedScenario.verification?.fixed?.passed ? "pass" : "pending"}` : "Select a failure to inspect" },
          ]).map((evidence, index) => (
            <div key={`${evidence.path}-${index}`} className="grid grid-cols-[24px_minmax(0,1fr)] gap-2 border-b border-white/[0.04] pb-2 last:border-0">
              <span className="font-mono text-[9px] text-zinc-700">{String(index + 1).padStart(2, "0")}</span>
              <div className="min-w-0"><p className="truncate font-mono text-[9px] text-emerald-300/80">{evidence.path}</p><p className="mt-1 line-clamp-2 break-words text-[9px] leading-relaxed text-zinc-600">{evidence.quote}</p></div>
            </div>
          ))}
        </div>
      </aside>
      </div>
    </section>
  );
}
