// Pure view logic for 技术信号矩阵 — kept out of the component so it can be unit-tested
// and so the panel file stays about rendering.
//
// The important invariant these functions protect: 弃权 (abstain) and 无数据 (na) are
// distinct from 中性 (neutral) and never contribute to a row's net. A row that abstained
// on half its columns is *less* certain, not neutral — and the UI must be able to say so.
import type { CSSProperties } from "react";
import type { SignalMatrixRow, SignalState } from "@/types";
import { DOWN_COLOR, UP_COLOR, mixColor } from "@/styles/theme";

export const STATE_GLYPH: Record<SignalState, string> = {
  bull: "多",
  bear: "空",
  neutral: "中",
  abstain: "弃",
  na: "—",
};

export const STATE_FULL: Record<SignalState, string> = {
  bull: "偏多",
  bear: "偏空",
  neutral: "中性",
  abstain: "弃权",
  na: "无数据",
};

/**
 * Cell fill by state.
 *
 * 中性 is left untinted on purpose: it means "this rule read the data and has no view",
 * and tinting it would put a wall of colour on screen that says nothing. 弃权 gets a
 * muted grey (a rule that declined is still information — it tells you the reading was
 * 超买/无趋势 rather than 震荡), and 无数据 is dimmed hardest.
 */
export function cellStyle(state: SignalState, dark: boolean): CSSProperties {
  const base = dark ? "#0b0e13" : "#ffffff";
  switch (state) {
    case "bull":
      return { background: mixColor(base, UP_COLOR, 0.18), color: UP_COLOR };
    case "bear":
      return { background: mixColor(base, DOWN_COLOR, 0.18), color: DOWN_COLOR };
    case "abstain":
      return {
        background: mixColor(base, "#8a919e", 0.08),
        color: dark ? "#7d8590" : "#8a919e",
      };
    case "na":
      return { color: dark ? "#4a525f" : "#b8bcc4" };
    default:
      return {};
  }
}

export type ViewFilter = "all" | "bull" | "bear" | "split" | "flat";
export type SortKey = "net" | "name" | "change" | "turnover";

export function filterRows(rows: SignalMatrixRow[], view: ViewFilter): SignalMatrixRow[] {
  switch (view) {
    case "bull":
      return rows.filter((r) => r.verdict === "偏多");
    case "bear":
      return rows.filter((r) => r.verdict === "偏空");
    case "split":
      return rows.filter((r) => r.verdict === "分歧");
    case "flat":
      return rows.filter((r) => r.verdict === "无方向" || r.verdict === "无数据");
    default:
      return rows;
  }
}

/**
 * ``net`` descending puts the strongest 偏多 at the top and the strongest 偏空 at the
 * bottom — the two ends of the list are the most decisive rows either way, which is what
 * a reader scanning for extremes wants.
 */
export function sortRows(rows: SignalMatrixRow[], key: SortKey): SignalMatrixRow[] {
  const out = [...rows];
  if (key === "name") out.sort((a, b) => a.name.localeCompare(b.name, "zh"));
  else if (key === "change") out.sort((a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity));
  else if (key === "turnover") out.sort((a, b) => (b.turnover ?? -1) - (a.turnover ?? -1));
  else out.sort((a, b) => b.net - a.net);
  return out;
}

/** Strongest (sign 1) / weakest (sign -1) row that actually voted and wasn't excluded.
 *  Rows excluded for 低流动/停牌 have real readings but shouldn't be crowned. */
export function extreme(rows: SignalMatrixRow[], sign: 1 | -1): SignalMatrixRow | null {
  const pool = rows.filter((r) => r.voted > 0 && !r.excluded);
  if (!pool.length) return null;
  return pool.reduce((best, r) => (sign * r.net > sign * best.net ? r : best));
}

/** Breadth strip segments, zero-count verdicts dropped so they take no width. */
export function breadthSegments(
  breadth: { bull: number; bear: number; split: number; flat: number },
): { label: string; n: number }[] {
  return [
    { label: "偏多", n: breadth.bull },
    { label: "偏空", n: breadth.bear },
    { label: "分歧", n: breadth.split },
    { label: "无方向", n: breadth.flat },
  ].filter((s) => s.n > 0);
}
