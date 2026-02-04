import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

type Row = {
  name: string;
  safety: number | null;
  utility: number | null;
  overall: number | null;
  p50: number | null;
  p95: number | null;
  audit: number | null;
};

function parsePercent(value: string): number | null {
  const trimmed = value.replace("%", "").trim();
  if (!trimmed || trimmed === "-") return null;
  const num = Number(trimmed);
  return Number.isFinite(num) ? num / 100 : null;
}

function parseNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "-") return null;
  const num = Number(trimmed);
  return Number.isFinite(num) ? num : null;
}

function parseLeaderboard(md: string): Row[] {
  const lines = md
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("|"));

  if (lines.length < 3) return [];

  const rows = lines.slice(2);
  const parsed: Row[] = [];

  for (const row of rows) {
    const cols = row.split("|").map((c) => c.trim()).filter(Boolean);
    if (cols.length < 7) continue;

    parsed.push({
      name: cols[0],
      safety: parsePercent(cols[1]),
      utility: parsePercent(cols[2]),
      overall: parsePercent(cols[3]),
      p50: parseNumber(cols[4]),
      p95: parseNumber(cols[5]),
      audit: parsePercent(cols[6]),
    });
  }

  return parsed;
}

async function readLeaderboard(): Promise<string | null> {
  const candidates = [
    path.resolve(process.cwd(), "eval", "LEADERBOARD.md"),
    path.resolve(process.cwd(), "..", "eval", "LEADERBOARD.md"),
    path.resolve(process.cwd(), "public", "leaderboard.md"),
    "/app/eval/LEADERBOARD.md",
  ];

  for (const p of candidates) {
    try {
      return await fs.readFile(p, "utf-8");
    } catch {
      // try next path
    }
  }

  return null;
}

export async function GET() {
  const md = await readLeaderboard();
  if (!md) {
    return NextResponse.json({ rows: [] }, { status: 200 });
  }

  return NextResponse.json({ rows: parseLeaderboard(md) }, { status: 200 });
}
