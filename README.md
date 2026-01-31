# 🛡️ SENTENIEL — Secure Control Plane for Tool‑Using AI Agents

![Senteniel Banner](docs/banner.png)

> **A production‑grade, agent‑safety and tool‑use control platform for autonomous AI systems — combining MCP‑based tool isolation, LangGraph and FSM orchestration, GraphRAG‑backed policy reasoning, and audit‑grade decision traces. Designed to evaluate and enforce safe agent execution at scale.**

---

![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-green)
![GraphQL](https://img.shields.io/badge/GraphQL-Control_Plane-purple)
![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-orange)
![FSM](https://img.shields.io/badge/Custom_FSM-Orchestration-lightgrey)
![MCP](https://img.shields.io/badge/MCP-Tool_Boundary-black)
![GraphRAG](https://img.shields.io/badge/GraphRAG-Policy_Reasoning-blue)
![Neo4j](https://img.shields.io/badge/Neo4j-Knowledge_Graph-brightgreen)
![Pinecone](https://img.shields.io/badge/Pinecone-Vector_Search-yellowgreen)
![Postgres](https://img.shields.io/badge/Postgres-Audit_DB-blue)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)
![Status](https://img.shields.io/badge/status-active_development-orange)

---

⭐ **Star this repository** — Senteniel is built as a reference system for safe, auditable agent execution.

---

## 🔥 Why Senteniel?

**Senteniel is not a chatbot, copilot, or demo agent.**  
It is a **control plane** for **tool‑using AI agents**.

As modern LLM agents gain the ability to:
- read files
- query logs
- open tickets
- modify repositories
- interact with production systems

**prompt injection and unsafe tool execution become real security risks.**

Senteniel exists to answer a single hard question:

> *“Should this agent be allowed to do this — and can we prove why?”*

---

## 🧠 About

Senteniel is an **agent‑security research and engineering platform** built to:

- enforce **least‑privilege tool use**
- prevent **prompt‑injection‑driven actions**
- require **human approval for risky operations**
- produce **audit‑grade reasoning traces**
- compare **LangGraph vs a Custom FSM** under identical safety constraints

It is **industry‑agnostic** and applicable to:
- FAANG‑scale internal tooling
- fintech, infra, and SRE platforms
- enterprise agent frameworks
- AI governance and security research

---

## 🏗️ Core Concepts

Senteniel enforces strict separation of concerns:

| Layer | Responsibility |
|------|----------------|
| **Agent** | Proposes actions |
| **Gateway (Senteniel)** | Decides if actions are allowed |
| **MCP Server** | Executes tools (sandboxed) |
| **Policy Engine** | Enforces RBAC / ABAC |
| **GraphRAG** | Grounds decisions in policy and incidents |
| **Audit Store** | Persists every decision |
| **Evaluation Harness** | Compares orchestrators |

---

## ✨ Key Features

### 🛡️ Agent Firewall (Control Plane)
- Intercepts **all agent tool calls**
- Enforces:
  - explicit allowlists
  - role‑based and environment‑based access
  - strict input validation
- Blocks unsafe execution **before tools are reached**

---

### 🔌 MCP‑Based Tool Boundary
- All tools exposed via a **sandboxed MCP server**
- Read‑only by default
- Write actions require explicit human approval
- No direct tool access from agents

This makes tool‑use safety **concrete and enforceable**, not theoretical.

---

### 🧠 Dual Orchestration Engines
Senteniel evaluates the **same agent logic** across two orchestration strategies:

- **LangGraph**
- **Custom Finite State Machine (FSM)**

Everything else remains identical:
- LLM
- tools
- policies
- retrieval
- evaluation harness

This enables a **fair, reproducible comparison**.

**Proof (current output):**

#### LangGraph (example)
```json
{
  "user_task": "list files",
  "plan": "Use fs.list_dir to inspect the sandbox",
  "tool_result": "[]",
  "final_answer": "Tool executed successfully. Result: []"
}
```

#### FSM (example)
```json
{
  "final_state": {
    "user_task": "list files",
    "plan": "List sandbox files",
    "tool": "fs.list_dir",
    "args": {
      "path": "/sandbox"
    },
    "decision": "ALLOW",
    "result": "[]"
  }
}
```

---

### 📚 GraphRAG‑Backed Policy Reasoning
- Policies, incidents, and tool contracts stored in a **knowledge graph**
- Relevant subgraphs retrieved at decision time
- Decisions are grounded with:
  - policy citations
  - prior incident references
  - explicit reasoning paths

---

### 🧾 Audit‑Grade Decision Traces
Every tool proposal produces a durable record:
- decision (ALLOW / BLOCK / APPROVAL_REQUIRED)
- rationale
- policy citations
- risk score
- redacted tool arguments
- timestamps

Nothing is implicit. Nothing is hidden.

---

### 📊 Evaluation & Leaderboards
Senteniel includes a built‑in evaluation harness to measure:

- prompt‑injection block rate
- unsafe execution rate
- false‑block rate
- task success rate
- latency
- tool calls per run

Results are compared across:
- LangGraph vs FSM
- different policy strictness profiles

---

## 🧩 System Architecture

```
┌──────────┐
│  Agent   │
└────┬─────┘
     │ Proposes tool call
     ▼
┌──────────────────┐
│ Senteniel Gateway │  (GraphQL)
│  - Policy Engine │
│  - Risk Scoring  │
│  - GraphRAG      │
└────┬─────────────┘
     │ Allowed
     ▼
┌──────────────┐
│ MCP Server   │  (Sandboxed tools)
└────┬─────────┘
     ▼
 Real / Mock Tools
```

---

## 🔄 How It Works

1. A user or system submits a task  
2. The agent proposes one or more tool calls  
3. Senteniel evaluates:
   - tool permissions
   - role and environment
   - untrusted input boundaries
   - policy constraints
4. GraphRAG retrieves relevant policies and prior incidents  
5. A decision is made and persisted  
6. Approved calls are forwarded to the MCP server  
7. Tool outputs are redacted and returned  

---

## 🗃️ Audit Database (Core Tables)

- **runs**
- **tool_calls**
- **decisions**

All schema changes are managed via Alembic migrations.

---

## 🖥️ User Interfaces

Senteniel provides a web UI for **security, platform, and infra teams**:

### 🔍 Dashboard
- active runs
- tool usage overview
- risk distribution

### 🛑 Approval Queue
- review pending write actions
- inspect diffs and intent
- approve or deny with justification

### 🧾 Decision Trace View
- full reasoning graph
- policy citations
- incident references

### 🏁 Leaderboard
- LangGraph vs FSM performance comparison
- safety vs utility trade‑offs

---

## 🛣️ Roadmap

### ✅ Phase 0 — System Spine
- Dockerized gateway and MCP server
- GraphQL control plane
- Audit logging
- Prometheus metrics
- Persisted audit logs with GraphQL read queries (runs, tool calls, decisions)

### 🚧 Phase 1 — Orchestration Comparison
- ✅ LangGraph runner (single-agent) — `POST /agent/run?task=...`
- ✅ FSM runner (deterministic baseline) — `POST /agent/fsm/run?task=...`
- ✅ Fairness rule enforced: same tools, same policies, same MCP boundary; only orchestrator differs

### 🚧 Phase 2 — GraphRAG Proof Mode
- Neo4j policy graph
- Incident grounding
- Decision explanation graphs

### 🚧 Phase 3 — Evaluation Harness
- Prompt‑injection test suite
- Leaderboards
- Regression safety tests

---

## 📌 Status

**Active development. Designed as a reference architecture for safe agent execution.**

---

## 🤝 Why This Project Matters

Senteniel targets one of the most urgent unsolved problems in modern AI systems:

> *How do we safely allow autonomous agents to act in the real world?*

This repository answers that question with **engineering rigor, explicit safety boundaries, and measurable evaluation** — not demos.
