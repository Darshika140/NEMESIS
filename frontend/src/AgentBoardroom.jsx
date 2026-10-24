import { useEffect, useMemo, useRef, useState } from "react";
import { streamInstructionReview } from "./api.js";

function AgentStatus({ children, tone = "neutral" }) {
  const colors = tone === "green"
    ? "border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-300"
    : tone === "red"
      ? "border-rose-400/20 bg-rose-400/[0.05] text-rose-300"
      : "border-white/10 bg-white/[0.025] text-slate-400";
  return <span className={`rounded-full border px-2 py-1 font-mono text-[9px] uppercase ${colors}`}>{children}</span>;
}

export default function AgentBoardroom({ scenario, provider }) {
  const [instruction, setInstruction] = useState("");
  const [events, setEvents] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const reviewController = useRef(null);

  useEffect(() => {
    reviewController.current?.abort();
    setEvents([]);
    setResult(null);
    setError("");
    setPending(false);
    return () => reviewController.current?.abort();
  }, [scenario?.id]);

  const testCases = useMemo(() => {
    if (!scenario) return [];
    return [
      scenario.mechanism,
      ...(scenario.claim_diff ?? []).map((claim) => claim.expected),
    ].filter(Boolean).slice(0, 20);
  }, [scenario]);

  async function submit(event) {
    event.preventDefault();
    if (!scenario || !instruction.trim() || pending || testCases.length === 0) return;

    setPending(true);
    setError("");
    setEvents([]);
    setResult(null);
    const controller = new AbortController();
    reviewController.current = controller;
    try {
      await streamInstructionReview(
        {
          instruction: instruction.trim(),
          failureEvidence: scenario,
          testCases,
          provider,
          maxIterations: 3,
        },
        (nextEvent) => {
          setEvents((current) => [...current, nextEvent]);
          if (nextEvent.type === "complete") setResult(nextEvent.result);
        },
        controller.signal,
      );
    } catch (requestError) {
      if (requestError.name !== "AbortError") setError(requestError.message);
    } finally {
      if (!controller.signal.aborted) setPending(false);
    }
  }

  const defenses = events.filter((event) => event.type === "fixer_proposed");
  const evaluations = events.filter((event) => event.type === "red_team_result");
  const latestPhase = events.at(-1)?.type;

  return (
    <section className="theme-panel overflow-hidden rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09]" aria-labelledby="agent-boardroom-title">
      <div className="border-b border-white/[0.07] px-5 py-4">
        <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Multi-agent adjudication</p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 id="agent-boardroom-title" className="text-sm font-semibold text-slate-100">Agent boardroom</h2>
            <p className="mt-1 text-[10px] text-slate-500">Fixer proposals are reviewed against only the selected failure’s supplied regression cases.</p>
          </div>
          <AgentStatus tone={result?.verified ? "green" : result ? "red" : "neutral"}>
            {pending ? "Review in progress" : result?.verified ? "Adjudicated · pass" : result ? "Adjudicated · unresolved" : provider === "ollama" ? "Local only" : "Groq"}
          </AgentStatus>
        </div>
      </div>

      {!scenario ? (
        <p className="p-5 text-xs text-slate-500">Select a detected failure to open a bounded review board.</p>
      ) : (
        <>
          <div className="grid gap-px bg-white/[0.06] md:grid-cols-2">
            <div className="theme-subpanel bg-black/15 p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div><p className="font-mono text-[9px] uppercase tracking-[0.16em] text-rose-300">Red Team · adjudicator</p><p className="mt-1 text-[10px] text-slate-600">{provider === "ollama" ? "Ollama local model" : "Groq critic model"}</p></div>
                <AgentStatus tone={evaluations.at(-1)?.passed ? "green" : "red"}>{pending && latestPhase === "red_team_started" ? "Evaluating" : evaluations.at(-1) ? evaluations.at(-1).passed ? "Pass" : "Gap found" : "Ready"}</AgentStatus>
              </div>
              <p className="mb-3 rounded-md border border-rose-400/10 bg-rose-400/[0.025] p-2.5 font-mono text-[9px] leading-relaxed text-slate-500">
                Evaluates {testCases.length} supplied case(s). This board does not generate jailbreak strings or execute attacks.
              </p>
              <div className="space-y-2">
                {evaluations.length ? evaluations.map((review) => (
                  <article key={`review-${review.iteration}`} className="rounded-md border border-white/[0.07] p-3">
                    <p className="mb-1 font-mono text-[9px] text-zinc-600">ROUND {review.iteration} · {review.model}</p>
                    <p className="text-[10px] leading-relaxed text-slate-300">{review.finding}</p>
                    {review.counterexample && <p className="mt-2 border-l border-amber-300/30 pl-2 text-[9px] text-amber-200/80">{review.counterexample}</p>}
                  </article>
                )) : <p className="text-[10px] text-slate-700">{pending && latestPhase === "red_team_started" ? "Reviewing supplied regression cases…" : "Adjudication findings will appear here."}</p>}
              </div>
            </div>
            <div className="theme-subpanel bg-black/15 p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div><p className="font-mono text-[9px] uppercase tracking-[0.16em] text-emerald-300">Fixer · defense</p><p className="mt-1 text-[10px] text-slate-600">{provider === "ollama" ? "Ollama local model" : "Groq fixer model"}</p></div>
                <AgentStatus tone={defenses.length ? "green" : "neutral"}>{pending && latestPhase === "fixer_started" ? "Drafting" : defenses.length ? `${defenses.length} proposal(s)` : "Ready"}</AgentStatus>
              </div>
              <div className="space-y-2">
                {defenses.length ? defenses.map((proposal) => (
                  <article key={`proposal-${proposal.iteration}`} className="rounded-md border border-emerald-400/10 bg-emerald-400/[0.02] p-3">
                    <p className="mb-2 font-mono text-[9px] text-zinc-600">ROUND {proposal.iteration} · {proposal.model}</p>
                    <pre className="whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-slate-300">{proposal.candidate_instruction}</pre>
                  </article>
                )) : <p className="text-[10px] text-slate-700">{pending ? "Waiting for the Fixer proposal…" : "Defensive instruction proposals will appear here."}</p>}
              </div>
            </div>
          </div>
          <form onSubmit={submit} className="space-y-3 border-t border-white/[0.07] p-4 sm:p-5">
            <label htmlFor="boardroom-instruction" className="block font-mono text-[10px] text-slate-500">Current agent instruction</label>
            <textarea id="boardroom-instruction" value={instruction} onChange={(event) => setInstruction(event.target.value)} maxLength={12000} rows={3} placeholder="Paste the instruction to revise…" className="w-full resize-y rounded-md border border-white/[0.08] bg-[#080c09] px-3 py-2.5 font-mono text-[10px] leading-relaxed text-slate-300 outline-none placeholder:text-slate-700 focus:border-emerald-300/30" />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="max-w-xl font-mono text-[9px] leading-relaxed text-slate-600">Review is limited to supplied evidence; approval is model adjudication, not test execution or deployment.</p>
              <button type="submit" disabled={!scenario || !instruction.trim() || pending || testCases.length === 0} className="inline-flex items-center gap-2 rounded-md bg-emerald-400 px-3.5 py-2.5 text-[10px] font-semibold text-[#04110a] transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-40">
                {pending && <span className="size-3 animate-spin rounded-full border border-emerald-950/30 border-t-emerald-950" />}
                {pending ? "Agents reviewing…" : "Start agent review"}
              </button>
            </div>
            {error && <p role="alert" className="rounded border border-rose-400/10 bg-rose-400/[0.04] p-2.5 text-[10px] text-rose-300">{error}</p>}
            {result && <p className={`rounded-md border p-3 font-mono text-[10px] ${result.verified ? "border-emerald-400/15 bg-emerald-400/[0.03] text-emerald-300" : "border-amber-300/15 bg-amber-300/[0.03] text-amber-200"}`}>{result.message}</p>}
          </form>
        </>
      )}
    </section>
  );
}
