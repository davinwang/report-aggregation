// Colored change text following CN convention (红涨绿跌), terminal-style with
// ▲/▼ direction marker and tabular numerals.
import type { CSSProperties } from "react";
import { changeColor } from "@/styles/theme";
import { fmtPct } from "@/hooks/useRelativeTime";

interface Props {
  value?: number | null;
  suffix?: string;
  showSign?: boolean;
  digits?: number;
  arrow?: boolean;
  style?: CSSProperties;
}

export default function ChangeText({ value, suffix = "%", showSign = true, digits = 2, arrow = true, style }: Props) {
  const color = changeColor(value);
  const text = value == null ? "-" : showSign ? fmtPct(value, digits) : `${value.toFixed(digits)}${suffix}`;
  const marker = !arrow || value == null || value === 0 ? "" : value > 0 ? "▲ " : "▼ ";
  return (
    <span className="num" style={{ color, ...style }}>
      {marker}
      {text}
    </span>
  );
}
