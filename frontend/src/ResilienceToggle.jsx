const modes = [
  { id: "groq", label: "Cloud", detail: "Groq" },
  { id: "ollama", label: "Local", detail: "Ollama" },
];

export default function ResilienceToggle({ provider, onChange, disabled = false }) {
  return (
    <div
      aria-label="Inference provider"
      className="inline-flex items-center rounded-full border border-white/10 bg-zinc-900/60 p-1 backdrop-blur-md"
    >
      {modes.map((mode) => {
        const selected = provider === mode.id;
        return (
          <button
            key={mode.id}
            type="button"
            role="switch"
            aria-checked={selected}
            aria-label={`${mode.label} inference via ${mode.detail}`}
            disabled={disabled}
            onClick={() => onChange(mode.id)}
            className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-[10px] transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-emerald-300/50 disabled:cursor-not-allowed disabled:opacity-50 ${
              selected
                ? "theme-segment-active bg-[#202722] text-zinc-100 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <span className={`size-1.5 rounded-full ${selected ? "bg-emerald-300 shadow-[0_0_8px_rgba(110,231,183,0.7)]" : "bg-slate-700"}`} />
            <span className="font-medium">{mode.label}</span>
            <span className="hidden font-mono opacity-60 sm:inline">{mode.detail}</span>
          </button>
        );
      })}
    </div>
  );
}
