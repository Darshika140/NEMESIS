const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request(path, options) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!response.ok) {
    let message = `API request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload.detail?.message ?? payload.detail ?? message;
    } catch {
      // Keep the HTTP status as a useful fallback when the server sends no JSON.
    }
    throw new Error(message);
  }

  return response.json();
}

export async function getLatestRun(signal) {
  const payload = await request("/api/latest-run", { signal });
  return payload.run;
}

export async function getScenario(scenarioId, signal) {
  const payload = await request(`/api/scenarios/${encodeURIComponent(scenarioId)}`, { signal });
  return payload.scenario;
}

export async function startRun({ mode = "live_llm", nScenarios = 4 } = {}) {
  const payload = await request("/api/run", {
    method: "POST",
    body: JSON.stringify({ mode, n_scenarios: nScenarios }),
  });
  return payload.run;
}

export async function sendDiagnosticMessage({ message, executionLogs, provider }) {
  return request("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      execution_logs: executionLogs,
      provider,
    }),
  });
}

export async function requestInstructionHeal({
  instruction,
  failureEvidence,
  testCases,
  provider,
  maxIterations = 3,
}) {
  return request("/api/heal", {
    method: "POST",
    body: JSON.stringify({
      instruction,
      failure_evidence: failureEvidence,
      test_cases: testCases,
      provider,
      max_iterations: maxIterations,
    }),
  });
}

export async function streamInstructionReview({ instruction, failureEvidence, testCases, provider, maxIterations = 3 }, onEvent, signal) {
  const response = await fetch(`${API_BASE_URL}/api/heal/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      instruction,
      failure_evidence: failureEvidence,
      test_cases: testCases,
      provider,
      max_iterations: maxIterations,
    }),
    signal,
  });

  if (!response.ok) {
    let message = `Agent review failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload.detail?.message ?? payload.detail ?? message;
    } catch {
      // Keep the HTTP status when the server did not return JSON.
    }
    throw new Error(message);
  }
  if (!response.body) throw new Error("Streaming responses are unavailable in this browser.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;

  function dispatch(block) {
    const data = block.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
    if (!data) return;
    const event = JSON.parse(data);
    if (event.type === "error") {
      throw new Error(event.detail?.message ?? event.detail ?? "Agent review failed.");
    }
    if (event.type === "complete") completed = true;
    onEvent(event);
  }

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    blocks.forEach(dispatch);
    if (done) break;
  }
  if (buffer.trim()) dispatch(buffer);
  if (!completed) throw new Error("Agent review stream ended before completion.");
}

export async function createAuditTrail({ scenario, signal }) {
  const payload = await request("/api/audits", {
    method: "POST",
    body: JSON.stringify({ scenario }),
    signal,
  });
  return payload.audits;
}
