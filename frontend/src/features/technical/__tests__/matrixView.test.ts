// Signal-matrix view logic. These assertions encode the semantics the table depends on:
// 弃权/无数据 are distinct from 中性 and never counted, and excluded rows never get crowned.
import { describe, expect, it } from "vitest";
import {
  STATE_FULL,
  STATE_GLYPH,
  breadthSegments,
  cellStyle,
  extreme,
  filterRows,
  sortRows,
} from "../matrixView";
import type { SignalMatrixRow, SignalState } from "@/types";

function row(partial: Partial<SignalMatrixRow> & { code: string }): SignalMatrixRow {
  return {
    name: partial.code,
    type: "stock",
    exchange: "SSE",
    date: "2026-09-15",
    close: 10,
    change_pct: 0,
    turnover: 1e8,
    signals: {},
    bulls: 0,
    bears: 0,
    neutrals: 0,
    abstains: 0,
    voted: 0,
    net: 0,
    verdict: "无方向",
    excluded: null,
    ...partial,
  };
}

describe("cellStyle", () => {
  it("gives 偏多 and 偏空 distinct tints", () => {
    expect(cellStyle("bull", false).color).not.toBe(cellStyle("bear", false).color);
  });

  it("leaves 中性 untinted — it means 'no view', not a reading", () => {
    expect(cellStyle("neutral", false)).toEqual({});
    expect(cellStyle("neutral", true)).toEqual({});
  });

  it("dims 无数据 harder than 弃权", () => {
    const na = cellStyle("na", false).color as string;
    const abstain = cellStyle("abstain", false).color as string;
    expect(na).not.toBe(abstain);
    // 无数据 has no background tint at all; 弃权 keeps a muted one.
    expect(cellStyle("na", false).background).toBeUndefined();
    expect(cellStyle("abstain", false).background).toBeTruthy();
  });

  it("works in both themes", () => {
    (["bull", "bear", "neutral", "abstain", "na"] as SignalState[]).forEach((s) => {
      expect(() => cellStyle(s, true)).not.toThrow();
      expect(() => cellStyle(s, false)).not.toThrow();
    });
  });
});

describe("labels", () => {
  it("gives every state a distinct glyph and a full label", () => {
    const states: SignalState[] = ["bull", "bear", "neutral", "abstain", "na"];
    expect(new Set(states.map((s) => STATE_GLYPH[s])).size).toBe(states.length);
    expect(new Set(states.map((s) => STATE_FULL[s])).size).toBe(states.length);
    expect(STATE_FULL.abstain).toBe("弃权");
    expect(STATE_FULL.na).toBe("无数据");
    // 中性 and 弃权 must not read the same to a user.
    expect(STATE_FULL.neutral).not.toBe(STATE_FULL.abstain);
  });
});

describe("filterRows", () => {
  const rows = [
    row({ code: "A", verdict: "偏多" }),
    row({ code: "B", verdict: "偏空" }),
    row({ code: "C", verdict: "分歧" }),
    row({ code: "D", verdict: "无方向" }),
    row({ code: "E", verdict: "无数据" }),
  ];

  it("passes everything through on 全部", () => {
    expect(filterRows(rows, "all")).toHaveLength(5);
  });

  it("filters by verdict", () => {
    expect(filterRows(rows, "bull").map((r) => r.code)).toEqual(["A"]);
    expect(filterRows(rows, "bear").map((r) => r.code)).toEqual(["B"]);
    expect(filterRows(rows, "split").map((r) => r.code)).toEqual(["C"]);
  });

  it("groups 无方向 with 无数据 under one filter", () => {
    expect(filterRows(rows, "flat").map((r) => r.code)).toEqual(["D", "E"]);
  });
});

describe("sortRows", () => {
  const rows = [
    row({ code: "A", net: -3, change_pct: 2.0, turnover: 50, name: "AAA" }),
    row({ code: "B", net: 5, change_pct: -1.0, turnover: 10, name: "BBB" }),
    row({ code: "C", net: 0, change_pct: 0.5, turnover: 90, name: "CCC" }),
  ];

  it("does not mutate its input", () => {
    const before = rows.map((r) => r.code);
    sortRows(rows, "net");
    expect(rows.map((r) => r.code)).toEqual(before);
  });

  it("sorts by net descending — strongest 偏多 first, strongest 偏空 last", () => {
    expect(sortRows(rows, "net").map((r) => r.code)).toEqual(["B", "C", "A"]);
  });

  it("sorts by change and turnover descending", () => {
    expect(sortRows(rows, "change").map((r) => r.code)).toEqual(["A", "C", "B"]);
    expect(sortRows(rows, "turnover").map((r) => r.code)).toEqual(["C", "A", "B"]);
  });

  it("puts null change_pct last rather than first", () => {
    const withNull = [...rows, row({ code: "D", change_pct: null })];
    expect(sortRows(withNull, "change").at(-1)?.code).toBe("D");
  });

  it("sorts by name", () => {
    expect(sortRows(rows, "name").map((r) => r.name)).toEqual(["AAA", "BBB", "CCC"]);
  });
});

describe("extreme", () => {
  const rows = [
    row({ code: "A", net: 4, voted: 5 }),
    row({ code: "B", net: -9, voted: 5 }),
    row({ code: "SKIP", net: 99, voted: 0 }),
    row({ code: "THIN", net: 50, voted: 8, excluded: "低流动" }),
  ];

  it("never crowns a row that did not vote", () => {
    expect(extreme(rows, 1)?.code).toBe("A");
  });

  it("never crowns an excluded row", () => {
    expect(extreme(rows, 1)?.code).not.toBe("THIN");
  });

  it("finds the weakest", () => {
    expect(extreme(rows, -1)?.code).toBe("B");
  });

  it("returns null when nothing voted", () => {
    const quiet = [row({ code: "Q", voted: 0, verdict: "无方向" })];
    expect(extreme(quiet, 1)).toBeNull();
    expect(extreme([], 1)).toBeNull();
  });
});

describe("breadthSegments", () => {
  it("drops zero-count verdicts so they take no width", () => {
    expect(breadthSegments({ bull: 3, bear: 0, split: 1, flat: 0 })).toEqual([
      { label: "偏多", n: 3 },
      { label: "分歧", n: 1 },
    ]);
  });

  it("returns nothing for an empty market", () => {
    expect(breadthSegments({ bull: 0, bear: 0, split: 0, flat: 0 })).toEqual([]);
  });
});
