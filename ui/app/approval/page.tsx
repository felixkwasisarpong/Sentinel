"use client";

import React, { useEffect, useState } from "react";
import { gql } from "@/lib/graphql";
import { Sora, Space_Grotesk } from "next/font/google";

const sora = Sora({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const space = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

type Decision = {
  decision: string;
  reason: string;
  policyCitations: string[];
  controlRefs: string[];
  incidentRefs: string[];
};

type PendingApproval = {
  id: string;
  toolName: string;
  createdAt: string;
  status: string;
  approvedAt: string | null;
  approvalNote: string | null;
  argsRedacted: any;
  decision: Decision | null;
};

type PendingApprovalsData = {
  pendingApprovals: PendingApproval[];
};

type LeaderboardRow = {
  name: string;
  safety: number | null;
  utility: number | null;
  overall: number | null;
  p50: number | null;
  p95: number | null;
  audit: number | null;
};

type MCPServer = {
  id: string;
  name: string;
  baseUrl: string;
  toolPrefix: string;
  createdAt: string;
};

type MCPServersData = {
  mcpServers: MCPServer[];
};

const PENDING_QUERY = `
query PendingApprovals($limit: Int!) {
  pendingApprovals(limit: $limit) {
    id
    toolName
    createdAt
    status
    approvedAt
    approvalNote
    argsRedacted
    decision {
      decision
      reason
      policyCitations
      controlRefs
      incidentRefs
    }
  }
}
`;

const APPROVE_MUTATION = `
mutation Approve($id: String!, $note: String) {
  approveToolCall(toolCallId: $id, note: $note) {
    toolCallId
    decision
    finalStatus
  }
}
`;

const DENY_MUTATION = `
mutation Deny($id: String!, $note: String) {
  denyToolCall(toolCallId: $id, note: $note) {
    toolCallId
    decision
    finalStatus
  }
}
`;

const MCP_SERVERS_QUERY = `
query MCPServers {
  mcpServers {
    id
    name
    baseUrl
    toolPrefix
    createdAt
  }
}
`;

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function Chip({ label, tone }: { label: string; tone?: "lime" | "amber" | "red" }) {
  const toneClass =
    tone === "lime"
      ? "border-lime-400/50 text-lime-200 bg-lime-500/10"
      : tone === "amber"
      ? "border-amber-400/50 text-amber-200 bg-amber-500/10"
      : tone === "red"
      ? "border-red-400/60 text-red-200 bg-red-500/10"
      : "border-white/10 text-white/70 bg-white/5";

  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${toneClass}`}>
      {label}
    </span>
  );
}

export default function ApprovalsPage() {
  const [items, setItems] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [leaderboardErr, setLeaderboardErr] = useState<string | null>(null);
  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [mcpErr, setMcpErr] = useState<string | null>(null);

  const pendingCount = items.length;

  async function load(limit = 50) {
    setLoading(true);
    setErr(null);
    try {
      const data = await gql<PendingApprovalsData>(PENDING_QUERY, { limit });
      setItems(data.pendingApprovals ?? []);
    } catch (e: any) {
      setErr(e?.message || "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(50);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadLeaderboard() {
      try {
        const res = await fetch("/api/leaderboard", { cache: "no-store" });
        const json = await res.json();
        if (!cancelled) {
          setLeaderboard(Array.isArray(json?.rows) ? json.rows : []);
        }
      } catch (e: any) {
        if (!cancelled) {
          setLeaderboardErr(e?.message || "Failed to load leaderboard");
        }
      }
    }

    loadLeaderboard();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadMcpServers() {
      try {
        const data = await gql<MCPServersData>(MCP_SERVERS_QUERY);
        if (!cancelled) {
          setMcpServers(data.mcpServers ?? []);
        }
      } catch (e: any) {
        if (!cancelled) {
          setMcpErr(e?.message || "Failed to load MCP servers");
        }
      }
    }

    loadMcpServers();
    return () => {
      cancelled = true;
    };
  }, []);

  async function approve(id: string) {
    const note = window.prompt("Approval note (optional):") ?? undefined;
    setBusyId(id);
    setErr(null);
    try {
      await gql(APPROVE_MUTATION, { id, note });
      // remove from queue optimistically
      setItems((prev) => prev.filter((x) => x.id !== id));
    } catch (e: any) {
      setErr(e?.message || "Approve failed");
    } finally {
      setBusyId(null);
    }
  }

  async function deny(id: string) {
    const note = window.prompt("Denial note (optional):") ?? undefined;
    setBusyId(id);
    setErr(null);
    try {
      await gql(DENY_MUTATION, { id, note });
      setItems((prev) => prev.filter((x) => x.id !== id));
    } catch (e: any) {
      setErr(e?.message || "Deny failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className={`${sora.className} min-h-screen bg-[#0b0b0b] text-white`}>
      <div className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 opacity-40">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.08)_0,_rgba(0,0,0,0)_60%)]" />
          <div className="absolute inset-0 bg-[linear-gradient(transparent_0%,_rgba(0,0,0,0.2)_40%,_rgba(0,0,0,0.6)_100%)]" />
          <div className="absolute inset-0 bg-[linear-gradient(to_right,_rgba(255,255,255,0.05)_1px,_transparent_1px),linear-gradient(to_bottom,_rgba(255,255,255,0.05)_1px,_transparent_1px)] [background-size:180px_180px]" />
        </div>

        <div className="relative mx-auto max-w-6xl px-6 py-12">
          <div className="flex flex-col gap-2">
            <span className="text-xs uppercase tracking-[0.3em] text-white/40">Approval Center</span>
            <h1 className={`${space.className} text-3xl font-semibold text-white sm:text-4xl`}>
              You can’t protect what you can’t see; you can only pprove what matters.
            </h1>
            <p className="max-w-2xl text-sm text-white/60">
              Live queue for approval-required tool calls and a safety leaderboard for orchestrators.
            </p>
          </div>

          <div className="mt-10 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
            <section className="rounded-2xl border border-white/10 bg-white/5 p-5 shadow-[0_0_60px_rgba(0,0,0,0.45)]">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] text-white/50">Approval Queue</div>
                  <div className={`${space.className} mt-2 text-2xl font-semibold`}>
                    Pending <span className="text-lime-300">{pendingCount}</span>
                  </div>
                </div>
                <button
                  onClick={() => load(50)}
                  className="rounded-full border border-white/20 px-4 py-2 text-xs uppercase tracking-[0.2em] text-white/80 hover:border-lime-300 hover:text-lime-200"
                  disabled={loading}
                >
                  {loading ? "Refreshing…" : "Refresh"}
                </button>
              </div>

              {err && (
                <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                  {err}
                </div>
              )}

              <div className="mt-6 space-y-4">
                {loading ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-6 text-sm text-white/60">
                    Loading approvals…
                  </div>
                ) : items.length === 0 ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-6 text-sm text-white/60">
                    No pending approvals 🎉
                  </div>
                ) : (
                  items.map((it) => (
                    <div
                      key={it.id}
                      className="rounded-xl border border-white/10 bg-[#0f0f0f] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02)]"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/50">
                            <span>{it.toolName}</span>
                            <Chip label={it.status} tone="amber" />
                          </div>
                          <div className="mt-3 text-xs text-white/50">{it.id}</div>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => approve(it.id)}
                            disabled={busyId === it.id}
                            className="rounded-full border border-lime-300/70 bg-lime-400/10 px-4 py-2 text-xs uppercase tracking-[0.2em] text-lime-200 hover:bg-lime-300/20 disabled:opacity-60"
                          >
                            {busyId === it.id ? "…" : "Approve"}
                          </button>
                          <button
                            onClick={() => deny(it.id)}
                            disabled={busyId === it.id}
                            className="rounded-full border border-red-400/60 bg-red-500/10 px-4 py-2 text-xs uppercase tracking-[0.2em] text-red-200 hover:bg-red-500/20 disabled:opacity-60"
                          >
                            {busyId === it.id ? "…" : "Deny"}
                          </button>
                        </div>
                      </div>

                      <div className="mt-4 grid gap-3 text-sm text-white/70 sm:grid-cols-3">
                        <div>
                          <div className="text-xs uppercase tracking-[0.2em] text-white/40">Created</div>
                          <div className="mt-1">{formatTime(it.createdAt)}</div>
                        </div>
                        <div className="sm:col-span-2">
                          <div className="text-xs uppercase tracking-[0.2em] text-white/40">Reason</div>
                          <div className="mt-1">{it.decision?.reason || "—"}</div>
                        </div>
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        {(it.decision?.policyCitations ?? []).map((p) => (
                          <Chip key={p} label={p} tone="lime" />
                        ))}
                        {(it.decision?.controlRefs ?? []).map((c) => (
                          <Chip key={c} label={c} tone="amber" />
                        ))}
                        {(it.decision?.incidentRefs ?? []).map((i) => (
                          <Chip key={i} label={i} tone="red" />
                        ))}
                      </div>

                      <details className="mt-4 text-xs text-white/60">
                        <summary className="cursor-pointer select-none text-white/70">
                          View redacted args
                        </summary>
                        <pre className="mt-2 overflow-auto rounded-lg border border-white/10 bg-black/40 p-3 text-[11px] text-white/70">
                          {JSON.stringify(it.argsRedacted ?? {}, null, 2)}
                        </pre>
                      </details>
                    </div>
                  ))
                )}
              </div>
            </section>

            <section className="rounded-2xl border border-white/10 bg-white/5 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] text-white/50">Leaderboard</div>
                  <div className={`${space.className} mt-2 text-2xl font-semibold`}>
                    Orchestrator Safety
                  </div>
                </div>
                <div className="rounded-full border border-lime-400/60 px-3 py-1 text-xs uppercase tracking-[0.2em] text-lime-200">
                  Live
                </div>
              </div>

              <div className="mt-6 space-y-4">
                {leaderboardErr && (
                  <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200">
                    {leaderboardErr}
                  </div>
                )}

                {leaderboard.length === 0 ? (
                  <div className="rounded-xl border border-white/10 bg-[#0f0f0f] p-4 text-sm text-white/60">
                    No leaderboard data yet. Run the eval to populate LEADERBOARD.md.
                  </div>
                ) : (
                  leaderboard.map((row) => {
                    const auditPct = row.audit != null ? Math.round(row.audit * 100) : null;
                    const safetyPct = row.safety != null ? Math.round(row.safety * 100) : null;
                    const utilityPct = row.utility != null ? Math.round(row.utility * 100) : null;
                    const p95 = row.p95 != null ? row.p95 : "-";
                    return (
                      <div
                        key={row.name}
                        className="rounded-xl border border-white/10 bg-[#0f0f0f] p-4"
                      >
                        <div className="flex items-center justify-between">
                          <div className="text-sm font-semibold">{row.name}</div>
                          <Chip
                            label={`${auditPct != null ? auditPct : "-"}% audit`}
                            tone="lime"
                          />
                        </div>
                        <div className="mt-4 grid grid-cols-3 gap-3 text-xs text-white/60">
                          <div>
                            <div className="uppercase tracking-[0.2em] text-white/40">Safety</div>
                            <div className="mt-1 text-white/80">
                              {safetyPct != null ? `${safetyPct}%` : "-"}
                            </div>
                          </div>
                          <div>
                            <div className="uppercase tracking-[0.2em] text-white/40">Utility</div>
                            <div className="mt-1 text-white/80">
                              {utilityPct != null ? `${utilityPct}%` : "-"}
                            </div>
                          </div>
                          <div>
                            <div className="uppercase tracking-[0.2em] text-white/40">p95 ms</div>
                            <div className="mt-1 text-white/80">{p95}</div>
                          </div>
                        </div>
                        <div className="mt-4 h-2 rounded-full bg-white/5">
                          <div
                            className="h-2 rounded-full bg-gradient-to-r from-lime-400 via-amber-400 to-red-500"
                            style={{ width: `${Math.min(100, safetyPct ?? 0)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <div className="mt-6 rounded-xl border border-white/10 bg-black/40 p-4 text-xs text-white/60">
                <div className="uppercase tracking-[0.2em] text-white/40">Scorecard</div>
                <div className="mt-2">
                  Safety pass rate, false-block rate, and audit completeness across the last eval run.
                </div>
              </div>

              <div className="mt-6 rounded-xl border border-white/10 bg-[#0f0f0f] p-4 text-xs text-white/60">
                <div className="uppercase tracking-[0.2em] text-white/40">Connected MCPs</div>
                {mcpErr && (
                  <div className="mt-2 rounded-lg border border-red-500/40 bg-red-500/10 p-2 text-red-200">
                    {mcpErr}
                  </div>
                )}
                {mcpServers.length === 0 ? (
                  <div className="mt-2 text-white/50">No MCP servers registered.</div>
                ) : (
                  <div className="mt-3 space-y-2">
                    {mcpServers.map((srv) => (
                      <div
                        key={srv.id}
                        className="rounded-lg border border-white/10 bg-black/30 p-3"
                      >
                        <div className="flex items-center justify-between text-sm text-white/80">
                          <span>{srv.name}</span>
                          <Chip label={srv.toolPrefix} tone="lime" />
                        </div>
                        <div className="mt-2 text-[11px] text-white/50">{srv.baseUrl}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
