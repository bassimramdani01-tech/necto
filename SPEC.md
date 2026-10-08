# necto

> *necto* — Latin: "I bind, I connect, I join."

**One-liner:** An open-source observability layer that renders multi-agent AI systems as a **live, explorable network graph** — who called whom, with which model, at what cost, and where the handoffs broke.

---

## The unique standpoint

> **necto treats the *system of agents* as the first-class object, not a linear trace.**

Existing tools (Langfuse, LangSmith, AgentOps) show you a waterfall of one request. necto shows you the **living topology** and the **messages flowing across it**. The graph is not a view of your data — the graph *is* the product.

Long-term ambition (v3): necto grows from *observing* interop between different agents/models into *facilitating* it — a neutral mesh layer where heterogeneous agents genuinely coordinate.

---

## The problem

Once you wire 3+ agents together you lose visibility:

1. **Topology is invisible** — the wiring lives only in code and fragmented logs.
2. **Handoffs fail silently** — a router sends a message to the wrong agent and nobody notices until the answer is wrong.
3. **Cost is opaque per-agent** — you see the total bill, not that "Agent B burns 80% of tokens."
4. **Framework lock-in hides everything** — each framework traces differently, or not at all.
5. **Debugging a run = reconstructing state by hand.**

---

## Who it's for

**Indie builders & solo devs** first — people assembling multi-agent prototypes and side projects. They need a tool that's a one-command install, looks impressive immediately, and explains *their own system back to them*.

---

## What necto is NOT (anti-goals)

- ❌ Not a linear trace viewer.
- ❌ Not a framework (we don't build agents — we observe them).
- ❌ Not an eval/benchmark platform.
- ❌ Not a builder or mesh layer — *yet* (that's the v3 moonshot).

---

## Core features

### MVP (proves the idea — ship this)
1. **Interactive agent graph** — nodes = agents/models/tools; edges = messages & handoffs with direction + weight.
2. **Live + replayable runs** — watch a conversation execute, scrub back through it.
3. **Edge drill-down** — click an edge → exact prompt/response, model, tokens, latency, cost.
4. **Adapters** — Python SDK for **LangGraph** + **OpenAI Agents SDK**; plus a generic JSON/OTel endpoint.
5. **Self-host** — one Docker Compose command.

### v2 (makes it sticky)
- **Diff view** — compare two runs to see why behavior changed.
- **Cost & latency rollups** — per agent, per model, per workflow.
- **Handoff anomaly flags** — "this edge usually succeeds but failed 40% today."

### v3 (the moonshot — the real "different agents working together")
- **Read-write graph** — rewire agents visually.
- **Mesh layer** — necto actually *carries* messages between heterogeneous agents/frameworks, not just observes them.

---

## Architecture

\`\`\`
Agent framework ─► necto SDK (Py/TS) ─► Ingestion API (OTel + JSON)
                                         │
                                         ▼
                                   Postgres (+ ClickHouse later)
                                         │
                                         ▼
                                Query/API layer
                                         │
                                         ▼
                    React + React Flow (graph rendering)
\`\`\`

**Principles:**
- **Language-agnostic core** — the graph model doesn't care if the agent is Python, TS, or custom.
- **Align with OpenTelemetry GenAI/Agent semantic conventions** — adopt an open standard instead of inventing a proprietary one.
- **Self-host first, always free** — this is open source and portfolio/community-first.

---

## The event schema (the moat)

Everything reduces to a tiny, framework-agnostic vocabulary. A run is a stream of:

\`\`\`json
{
  "run_id": "r_01",
  "ts": "2025-01-15T10:00:00Z",
  "event": "handoff",
  "from": { "kind": "agent", "id": "router", "model": "gpt-4o-mini" },
  "to":   { "kind": "agent", "id": "researcher" },
  "payload": { "tokens": 1420, "latency_ms": 310, "cost_usd": 0.0031 },
  "content": "Summarize the paper and cite sources"
}
\`\`\`

Framework adapters translate their native events → this schema. **Interoperability is the moat.**

---

## Differentiation

| Player | What it is | necto's angle |
|---|---|---|
| Langfuse | OSS trace-first observability | **Topology/network-first** |
| LangSmith | LangChain commercial platform | **Cross-framework, free** |
| AgentOps | Agent observability | **Open graph + self-host + neutrality** |
| Flowise/Langflow | Visual *builders* | necto *explains*; they build (complementary) |

---

## Roadmap

1. **Spec + schema frozen** (now) — this doc + event schema v1.
2. **Rich fake dataset first** — hard-code a beautiful demo run so the landing GIF is impressive *before* adapters exist.
3. **MVP sprint** — SDK → ingestion → React Flow graph rendering a live run.
4. **Adapters** — LangGraph, then OpenAI Agents SDK.
5. **Validation** — 3 real builders run it on their own agents; watch them debug.
6. **Launch** — README with animated demo, Docker one-liner, "why not Langfuse" section; post to r/LocalLLaMA, r/LangChain, Show HN.

---

## Success (what "it worked" looks like)

- ⭐ GitHub stars and a handful of **external contributors**.
- Real strangers running it on **their** agents and reporting bugs/ideas.
- A **shareable demo** that makes someone say "wait, can I see that with my system?"
- Personal proof-of-work for the portfolio — and a community that outlives any single job.

---

## Risks

- **Crowded, fast-moving category** — framework APIs break adapters; incumbents ship weekly.
- **"Better visualization" is subjective** — must be validated on *real* failure modes, not demo sugar.
- **Solo OSS is a grind** — scope the MVP ruthlessly; the demo is the first deliverable, not the last.

---

## The bet

If necto wins on **the live network view** and **cross-framework neutrality**, it carves out a real wedge between trace-first observers and visual builders. If it doesn't, it's just a prettier Langfuse — and the market won't care.
