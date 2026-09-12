// Page shell: header (title + description + actions) above content.
import type { ReactNode } from "react";
import { Space, Typography } from "antd";

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
          marginBottom: 14,
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {title}
          </Typography.Title>
          {description && <div className="muted" style={{ marginTop: 4 }}>{description}</div>}
        </div>
        {extra && <Space wrap>{extra}</Space>}
      </div>
      {children}
    </div>
  );
}
