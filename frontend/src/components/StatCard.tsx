// Compact terminal stat card: uppercase label + large mono value + signed change.
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
    <Card size="small" loading={loading} styles={{ body: { padding: "10px 12px" } }}>
      <div className="stat-label">{title}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="num" style={{ fontSize: 22, fontWeight: 600 }}>
          {value}
        </span>
        {change != null && <ChangeText value={change} />}
      </div>
      {footer && (
        <div className="muted" style={{ marginTop: 4 }}>
          {footer}
        </div>
      )}
    </Card>
  );
}
