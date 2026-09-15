// Bloomberg-style ticker tape: scrolling index quotes pinned under the header,
// with a live clock + latest trade date on the right. Data: /api/market/dashboard.
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDashboard } from "@/api";
import ChangeText from "./ChangeText";

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    <span className="num" style={{ color: "var(--srp-brand)", fontWeight: 600 }}>
      {pad(now.getHours())}:{pad(now.getMinutes())}:{pad(now.getSeconds())}
    </span>
  );
}

export default function TickerTape() {
  const { data } = useQuery({
    queryKey: ["market", "ticker-tape"],
    queryFn: () => getDashboard({}),
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: 1,
  });

  const indices = data?.indices ?? [];
  // Duplicate the strip so translateX(-50%) loops seamlessly.
  const loop = [...indices, ...indices];
  const duration = Math.max(30, indices.length * 7);

  return (
    <div
      className="ticker-tape"
      style={{
        position: "sticky",
        top: 46,
        zIndex: 19,
        height: 28,
        display: "flex",
        alignItems: "center",
        background: "var(--srp-bg)",
        borderBottom: "1px solid var(--srp-border)",
        fontSize: 11,
      }}
    >
      {indices.length ? (
        <div
          className="ticker-track"
          style={{ ["--ticker-duration" as string]: `${duration}s` }}
        >
          {loop.map((idx, i) => (
            <span key={`${idx.code}-${i}`} className="ticker-item">
              <span style={{ color: "var(--srp-muted)" }}>{idx.name}</span>
              <span className="num">{idx.close?.toFixed(2) ?? "-"}</span>
              <ChangeText value={idx.change_pct} />
            </span>
          ))}
        </div>
      ) : (
        <span className="muted" style={{ padding: "0 12px" }}>
          行情跑马灯 · 完成数据采集后滚动显示指数行情
        </span>
      )}

      <div
        style={{
          position: "absolute",
          right: 0,
          top: 0,
          bottom: 0,
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "0 12px",
          background: "var(--srp-bg)",
          borderLeft: "1px solid var(--srp-border)",
        }}
      >
        {data?.latestTradeDate && (
          <span className="num" style={{ color: "var(--srp-muted)" }}>
            {data.latestTradeDate}
          </span>
        )}
        <Clock />
      </div>
    </div>
  );
}
