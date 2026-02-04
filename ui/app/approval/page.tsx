"use client";

import React, { useEffect, useMemo, useState } from "react";
import { gql } from "@/lib/graphql";

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
  approvedBy?: string | null;
  approvalNote: string | null;
  argsRedacted: any;
  decision: Decision | null;
};

type PendingApprovalsData = {
  pendingApprovals: PendingApproval[];
};

const PENDING_QUERY = `
query PendingApprovals($limit: Int!) {
  pendingApprovals(limit: $limit) {
    id
    toolName
    createdAt
    status
    approvedAt
    approvedBy
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
    id
    status
    approvedAt
    approvedBy
    approvalNote
  }
}
`;

const DENY_MUTATION = `
mutation Deny($id: String!, $note: String) {
  denyToolCall(toolCallId: $id, note: $note) {
    id
    status
    approvedAt
    approvedBy
    approvalNote
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

function Chip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs">
      {label}
    </span>
  );
}

export default function ApprovalsPage() {
  const [items, setItems] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

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

  const count = items.length;

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Approval Queue</h1>
          <p className="mt-1 text-sm text-slate-600">
            Review tool calls requiring human approval (APPROVAL_REQUIRED).{" "}
            <span className="font-medium">{count}</span> pending.
          </p>
        </div>

        <button
          onClick={() => load(50)}
          className="rounded-lg border px-4 py-2 text-sm hover:bg-slate-50"
          disabled={loading}
        >
          Refresh
        </button>
      </div>

      {err && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {err}
        </div>
      )}

      <div className="mt-6 overflow-hidden rounded-xl border">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3">Tool</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3">Reason</th>
              <th className="px-4 py-3">Citations</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>

          <tbody>
            {loading ? (
              <tr>
                <td className="px-4 py-6 text-slate-600" colSpan={6}>
                  Loading…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-slate-600" colSpan={6}>
                  No pending approvals 🎉
                </td>
              </tr>
            ) : (
              items.map((it) => (
                <React.Fragment key={it.id}>
                  <tr className="border-t">
                    <td className="px-4 py-3 font-mono text-xs">
                      {it.toolName}
                      <div className="mt-1 text-[11px] text-slate-500">
                        {it.id}
                      </div>
                    </td>

                    <td className="px-4 py-3">
                      <Chip label={it.status} />
                    </td>

                    <td className="px-4 py-3 text-slate-700">
                      {formatTime(it.createdAt)}
                    </td>

                    <td className="px-4 py-3 text-slate-700">
                      {it.decision?.reason || "—"}
                    </td>

                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        {(it.decision?.policyCitations ?? []).map((p) => (
                          <Chip key={p} label={p} />
                        ))}
                        {(it.decision?.controlRefs ?? []).map((c) => (
                          <Chip key={c} label={c} />
                        ))}
                        {(it.decision?.incidentRefs ?? []).map((i) => (
                          <Chip key={i} label={i} />
                        ))}
                      </div>
                    </td>

                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => approve(it.id)}
                          disabled={busyId === it.id}
                          className="rounded-lg border px-3 py-1.5 text-xs hover:bg-slate-50 disabled:opacity-60"
                        >
                          {busyId === it.id ? "…" : "Approve"}
                        </button>
                        <button
                          onClick={() => deny(it.id)}
                          disabled={busyId === it.id}
                          className="rounded-lg border px-3 py-1.5 text-xs hover:bg-slate-50 disabled:opacity-60"
                        >
                          {busyId === it.id ? "…" : "Deny"}
                        </button>
                      </div>
                    </td>
                  </tr>

                  <tr className="bg-white">
                    <td className="px-4 pb-5 pt-2 text-xs text-slate-600" colSpan={6}>
                      <details>
                        <summary className="cursor-pointer select-none text-slate-700">
                          Details (redacted args)
                        </summary>
                        <pre className="mt-2 overflow-auto rounded-lg border bg-slate-50 p-3 text-[11px]">
                          {JSON.stringify(it.argsRedacted ?? {}, null, 2)}
                        </pre>
                      </details>
                    </td>
                  </tr>
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}