import { useEffect, useState } from "react";
import { createAuditTrail } from "./api.js";

function highlightUnsupported(claim, expected) {
  const expectedCounts = new Map();
  (expected.match(/[A-Za-z0-9_'’-]+/g) ?? []).forEach((word) => {
    const key = word.toLocaleLowerCase();
    expectedCounts.set(key, (expectedCounts.get(key) ?? 0) + 1);
  });
  return (claim.match(/\s+|[A-Za-z0-9_'’-]+|[^\sA-Za-z0-9_'’-]+/g) ?? [claim]).map((part, index) => {
    if (!/[A-Za-z0-9_'’-]/.test(part)) return <span key={index}>{part}</span>;
    const key = part.toLocaleLowerCase();
    const count = expectedCounts.get(key) ?? 0;
    if (count > 0) {
      expectedCounts.set(key, count - 1);
      return <span key={index}>{part}</span>;
    }
    return <mark key={index} className="audit-unsupported-token rounded bg-rose-500/15 px-0.5 text-rose-700">{part}</mark>;
  });
}

function downloadAudit(audits) {
  const content = JSON.stringify({ audits }, null, 2);
  const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `nemesis-audit-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function AuditTrailViewer({ scenario }) {
  const [audits, setAudits] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!scenario) {
      setAudits([]);
      setError("");
      setPending(false);
      return undefined;
    }
    const controller = new AbortController();
    setAudits([]);
    setError("");
    setPending(true);
    createAuditTrail({
      scenario,
      signal: controller.signal,
    })
      .then(setAudits)
      .catch((requestError) => {
        if (requestError.name !== "AbortError") setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setPending(false);
      });
    return () => controller.abort();
  }, [scenario]);

  return (
    <section className="theme-panel overflow-hidden rounded-xl border border-white/[0.09] bg-gradient-to-br from-[#0d120f] to-[#080b09]" aria-labelledby="audit-trail-title">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] px-5 py-4">
        <div>
          <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-emerald-400/80">Compliance record</p>
          <h2 id="audit-trail-title" className="text-sm font-semibold text-slate-100">Claim-level audit trail</h2>
        </div>
        <button type="button" onClick={() => downloadAudit(audits)} disabled={!audits.length} className="rounded-md border border-white/10 px-3 py-2 font-mono text-[9px] text-slate-400 transition hover:border-emerald-400/20 hover:text-emerald-300 disabled:cursor-not-allowed disabled:opacity-40">Export JSON</button>
      </div>
      <div className="space-y-3 p-4 sm:p-5">
        {pending && <p role="status" className="animate-pulse font-mono text-[10px] text-zinc-500">Preparing audit from recorded claim diffs…</p>}
        {error && <p role="alert" className="rounded border border-rose-400/10 bg-rose-400/[0.04] p-2.5 text-[10px] text-rose-300">{error}</p>}
        {!scenario && !pending && <p className="text-xs text-slate-500">Select a failure with a recorded claim diff to generate a compliance record.</p>}
        {scenario && !pending && !error && audits.length === 0 && <p className="text-xs text-slate-500">No unsupported claims were recorded for this scenario.</p>}
        {audits.map((audit, index) => {
          const source = scenario.claim_diff?.find((claim) => claim.original === audit.isolated_claim);
          return (
            <article key={`${audit.timestamp}-${index}`} className="rounded-lg border border-white/[0.08] bg-black/[0.08]">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] px-4 py-3">
                <span className="font-mono text-[9px] uppercase tracking-wider text-emerald-300">AUDIT {String(index + 1).padStart(3, "0")} · UNSUPPORTED CLAIM</span>
                <span className="font-mono text-[9px] text-zinc-500">{new Date(audit.timestamp).toLocaleString()}</span>
              </div>
              <div className="grid gap-3 p-4 md:grid-cols-2">
                <div>
                  <p className="mb-2 font-mono text-[9px] uppercase tracking-wider text-zinc-500">Isolated claim · unsupported tokens highlighted</p>
                  <p className="rounded-md border border-rose-400/10 bg-rose-400/[0.025] p-3 font-mono text-[11px] leading-relaxed text-slate-300">{highlightUnsupported(audit.isolated_claim, source?.expected ?? "")}</p>
                </div>
                <div>
                  <p className="mb-2 font-mono text-[9px] uppercase tracking-wider text-zinc-500">Divergence reason</p>
                  <p className="rounded-md border border-white/[0.07] p-3 text-[11px] leading-relaxed text-slate-400">{audit.divergence_reason}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-white/[0.06] px-4 py-2.5 font-mono text-[9px] text-zinc-600">
                <span>model_version: <span className="text-zinc-400">{audit.model_version}</span></span>
                <span>timestamp: <span className="text-zinc-400">{audit.timestamp}</span></span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
