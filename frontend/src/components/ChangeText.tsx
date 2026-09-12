// Colored change text following CN convention (红涨绿跌).
import type { CSSProperties } from "react";
import { changeColor } from "@/styles/theme";
import { fmtPct } from "@/hooks/useRelativeTime";

interface Props {
  value?: number | null;
  suffix?: string;
  showSign?: boolean;
  digits?: number;
  style?: CSSProperties;
}

export default function ChangeText({ value, suffix = "%", showSign = true, digits = 2, style }: Props) {
  const color = changeColor(value);
  const text = value == null ? "-" : showSign ? fmtPct(value, digits) : `${value.toFixed(digits)}${suffix}`;
  return <span style={{ color, fontVariantNumeric: "tabular-nums", ...style }}>{text}</span>;
}
