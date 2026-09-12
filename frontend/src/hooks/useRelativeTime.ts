// Relative-time formatting (e.g. "3小时前") using dayjs, with absolute fallback.
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import "dayjs/locale/zh-cn";

dayjs.extend(relativeTime);
dayjs.locale("zh-cn");

export function relTime(input?: string | null): string {
  if (!input) return "-";
  const d = dayjs(input);
  if (!d.isValid()) return String(input);
  return d.fromNow();
}

export function fmtDate(input?: string | null, fmt = "YYYY-MM-DD"): string {
  if (!input) return "-";
  const d = dayjs(input);
  return d.isValid() ? d.format(fmt) : String(input);
}

export function fmtNum(v?: number | null, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "-";
  return v.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

// Format large CNY amounts as 万/亿.
export function fmtAmount(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return "-";
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(2)}万`;
  return v.toFixed(2);
}

export function fmtPct(v?: number | null, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "-";
  const s = v > 0 ? "+" : "";
  return `${s}${v.toFixed(digits)}%`;
}
