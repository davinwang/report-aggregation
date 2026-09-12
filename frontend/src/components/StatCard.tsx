// Compact stat card used across the dashboard.
import { Card } from "antd";
import type { ReactNode } from "react";
import ChangeText from "./ChangeText";

interface Props {
  title: ReactNode;
  value: ReactNode;
  change?: number | null;
  footer?: ReactNode;
  loading?: boolean;
}

export default function StatCard({ title, value, change, footer, loading }: Props) {
  return (
    <Card size="small" loading={loading} styles={{ body: { padding: 14 } }}>
      <div className="muted" style={{ marginBottom: 6 }}>
        {title}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 22, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</span>
        {change != null && <ChangeText value={change} />}
      </div>
      {footer && <div className="muted" style={{ marginTop: 6 }}>{footer}</div>}
    </Card>
  );
}
