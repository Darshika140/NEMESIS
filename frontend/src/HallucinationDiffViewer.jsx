function DiffColumn({ label, value, tone }) {
  return (
    <div className={`min-w-0 overflow-hidden rounded-lg border ${tone === "red" ? "border-rose-400/15 bg-[#0b090a]" : "border-emerald-400/15 bg-[#080d0a]"}`}>
      <div className={`flex items-center gap-2 border-b px-4 py-3 font-mono text-[9px] uppercase tracking-[0.16em] ${tone === "red" ? "border-rose-400/10 text-zinc-500" : "border-emerald-400/10 text-zinc-500"}`}>
        <span className={tone === "red" ? "text-rose-400" : "text-emerald-400"}>{tone === "red" ? "−" : "+"}</span>
        {label}
      </div>
      <div className="grid grid-cols-[34px_minmax(0,1fr)] font-mono text-[10px] leading-6">
        <div aria-hidden="true" className="border-r border-white/[0.04] px-2 py-3 text-right text-zinc-700">16<br />17<br />18</div>
        <p className="whitespace-pre-wrap break-words px-3 py-3 text-slate-300">{value || "No response recorded."}</p>
      </div>
    </div>
  );
}

export default function HallucinationDiffViewer({ scenario }) {
  const diffs = scenario?.claim_diff ?? [];
  if (!scenario || diffs.length === 0) {
    return (
      <section className="theme-panel rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09] p-5">
        <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Hallucination diff</p>
        <p className="mt-2 text-xs text-slate-500">Select a failure with a recorded claim diff to inspect the divergence.</p>
      </section>
    );
  }

  return (
    <section className="theme-panel rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09] p-5 sm:p-6" aria-labelledby="claim-diff-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Hallucination diff</p>
          <h2 id="claim-diff-title" className="mt-1 text-sm font-semibold text-slate-100">{scenario.title}</h2>
        </div>
      </div>
      <div className="space-y-3">
        {diffs.map((diff, index) => (
          <div key={`${diff.status}-${index}`}>
            <div className="mb-2 flex justify-end">
              <span className={`rounded-full border px-2.5 py-1 font-mono text-[9px] ${diff.status === "unsupported" ? "border-emerald-400/20 bg-emerald-400/[0.04] text-emerald-300" : "border-amber-300/15 text-amber-200"}`}>
                claim {index + 1} · {diff.status}
              </span>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <DiffColumn label={diff.status === "unsupported" ? "Original claim · unsupported" : "Original output"} value={diff.original} tone="red" />
              <DiffColumn label="Verified agent response" value={diff.fixed} tone="green" />
            </div>
            <div className="mt-2 rounded-lg border border-white/[0.07] bg-black/20 px-4 py-3">
              <p className="mb-1 font-mono text-[9px] uppercase tracking-wider text-emerald-300/80">Ground truth</p>
              <p className="font-mono text-[10px] leading-relaxed text-slate-400">{diff.expected}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
