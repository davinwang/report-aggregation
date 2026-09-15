// Page shell: terminal-style header (amber-bar title + description + actions) above content.
import type { ReactNode } from "react";
import { Space } from "antd";

interface Props {
  title: ReactNode;
  description?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
}

export default function PageContainer({ title, description, extra, children }: Props) {
  return (
    <div className="page-container">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: 12,
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div className="page-title">{title}</div>
          {description && <div className="muted" style={{ marginTop: 4 }}>{description}</div>}
        </div>
        {extra && (
          <Space wrap size={6}>
            {extra}
          </Space>
        )}
      </div>
      {children}
    </div>
  );
}
