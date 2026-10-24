import { useEffect, useState } from "react";
import { requestInstructionHeal } from "./api.js";

export default function SelfHealingPanel({ scenario, provider }) {
  const [instruction, setInstruction] = useState("");
  const [result, setResult] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setResult(null);
    setError("");
  }, [scenario?.id]);

  async function submit(event) {
    event.preventDefault();
    if (!scenario || !instruction.trim() || pending) return;

    setPending(true);
    setError("");
    setResult(null);
    try {
      const testCases = [
        scenario.mechanism,
        ...(scenario.claim_diff ?? []).map((claim) => claim.expected),
      ].filter(Boolean);
      setResult(
        await requestInstructionHeal({
          instruction: instruction.trim(),
          failureEvidence: scenario,
          testCases,
          provider,
        }),
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="theme-panel overflow-hidden rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09]" aria-labelledby="self-healing-title">
      <div className="border-b border-white/[0.07] px-5 py-4">
        <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Adversarial multi-agent review</p>
        <h2 id="self-healing-title" className="mt-1 text-sm font-semibold text-slate-100">Instruction self-healing</h2>
        <p className="mt-1 text-[10px] text-slate-500">Fixer drafts a replacement; Red Team attacks it against this failure.</p>
      </div>

      {!scenario ? (
        <p className="p-4 text-xs text-slate-600">Select a failure to provide evidence and regression expectations.</p>
      ) : (
        <form onSubmit={submit} className="space-y-3 p-4">
          <label htmlFor="agent-instruction" className="block font-mono text-[10px] text-slate-500">
            Current agent instruction
          </label>
          <textarea
            id="agent-instruction"
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            maxLength={12000}
            rows={3}
            placeholder="Paste the instruction you want the Fixer to revise…"
            className="w-full resize-y rounded-md border border-white/[0.08] bg-[#080c09] px-3 py-2.5 font-mono text-[10px] leading-relaxed text-slate-300 outline-none placeholder:text-slate-700 focus:border-emerald-300/30"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-[9px] text-slate-600">
              {provider === "ollama" ? "Local Ollama · remains on this machine" : "Groq Cloud · sends provided evidence to Groq"}
            </span>
            <button
              type="submit"
              disabled={pending || !instruction.trim()}
              className="inline-flex items-center gap-2 rounded-md border border-emerald-300/20 bg-emerald-300/[0.06] px-3 py-2 text-[10px] font-medium text-emerald-200 transition hover:bg-emerald-300/[0.12] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {pending && <span className="size-3 animate-spin rounded-full border border-emerald-200/30 border-t-emerald-200" />}
              {pending ? "Reviewing…" : "Draft & red-team"}
            </button>
          </div>
          <p className="font-mono text-[9px] leading-relaxed text-slate-700">
            This returns instruction text only. It does not edit files or execute the generated regression test.
          </p>
          {error && <p role="alert" className="rounded border border-rose-400/10 bg-rose-400/[0.04] p-2.5 text-[10px] text-rose-300">{error}</p>}
          {result && (
            <div className={`rounded-lg border p-3 ${result.verified ? "border-emerald-400/15 bg-emerald-400/[0.03]" : "border-amber-300/15 bg-amber-300/[0.03]"}`}>
              <div className="flex items-center justify-between gap-2">
                <span className={`font-mono text-[10px] font-semibold ${result.verified ? "text-emerald-300" : "text-amber-200"}`}>
                  {result.verified ? "RED TEAM APPROVED" : "NOT VERIFIED"}
                </span>
                <span className="font-mono text-[9px] text-slate-600">{result.provider} · {result.iterations.length} iteration(s)</span>
              </div>
              <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-black/20 p-2.5 font-mono text-[10px] leading-relaxed text-slate-300">{result.proposed_instruction}</pre>
              <ul className="mt-2 space-y-1.5">
                {result.iterations.map((iteration) => (
                  <li key={iteration.iteration} className="font-mono text-[9px] leading-relaxed text-slate-500">
                    <span className={iteration.red_team_passed ? "text-emerald-300" : "text-rose-300"}>R{iteration.iteration} {iteration.red_team_passed ? "PASS" : "REJECT"}</span>
                    {" · "}{iteration.finding}
                    {iteration.counterexample && <span className="block pl-6 text-slate-600">counterexample: {iteration.counterexample}</span>}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[9px] leading-relaxed text-slate-600">{result.message} Model approval is not execution proof.</p>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
