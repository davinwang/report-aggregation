// Per-page data freshness + refresh control (replaces the old global header
// refresh button): shows when THIS page's data was last ingested and a button
// that refetches only this page's queries.
//
// Two clocks, clearly separated:
//  - `feeds` given  → main tag shows the data's own update time (newest
//    last_success_at across the listed feeds, from GET /health/deep — i.e.
//    when the backend last successfully ingested it). All pages share one
//    cached /health/deep query (staleTime 60s), so the extra cost is one
//    small request per minute at most.
//  - fallback / tooltip → react-query `dataUpdatedAt` (= when THIS page last
//    fetched), kept as secondary info.
//
// The spinner reflects any in-flight refetch (SSE-driven included).
import { useEffect, useState } from "react";
import { Button, Tag, Tooltip } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryKey } from "@tanstack/react-query";
import dayjs from "dayjs";
import { getHealthDeep } from "@/api";

interface Props {
  /** Query-key prefixes considered "this page", e.g. [["market"], ["flow"]]. */
  queryKeys: QueryKey[];
  /** Label prefix, defaults to 更新. */
  label?: string;
  /** Feed names in data_freshness (see /health/deep). When given, the main
   *  tag shows the data's ingest time instead of the page fetch time. */
  feeds?: string[];
}

function keyMatches(key: QueryKey, prefixes: QueryKey[]): boolean {
  return prefixes.some((prefix) =>
    (prefix as readonly unknown[]).every((v, i) => (key as readonly unknown[])[i] === v),
  );
}

export default function PageRefresh({ queryKeys, label = "更新", feeds }: Props) {
  const queryClient = useQueryClient();
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [fetching, setFetching] = useState(false);

  const health = useQuery({
    queryKey: ["_page_refresh_health"],
    queryFn: getHealthDeep,
    enabled: !!feeds?.length,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  useEffect(() => {
    const cache = queryClient.getQueryCache();
    const sync = () => {
      const queries = cache.getAll().filter((q) => keyMatches(q.queryKey, queryKeys));
      const times = queries.map((q) => q.state.dataUpdatedAt).filter((t) => t > 0);
      if (times.length) setUpdatedAt(Math.max(...times));
      setFetching(queries.some((q) => q.state.fetchStatus === "fetching"));
    };
    sync();
    return cache.subscribe(sync);
  }, [queryClient, queryKeys]);

  // Newest ingest time across the requested feeds (data's own clock).
  let dataMs: number | null = null;
  let dataDate: string | null = null;
  if (feeds?.length) {
    for (const f of feeds) {
      const fr = health.data?.freshness?.[f];
      if (!fr?.last_success_at) continue;
      const t = dayjs(fr.last_success_at).valueOf();
      if (!dataMs || t > dataMs) dataMs = t;
      if (fr.latest_data_date && (!dataDate || fr.latest_data_date > dataDate)) dataDate = fr.latest_data_date;
    }
  }

  const showDataTime = dataMs != null;
  const mainTime = showDataTime
    ? dayjs(dataMs).format("MM-DD HH:mm")
    : updatedAt
      ? dayjs(updatedAt).format("HH:mm:ss")
      : "-";
  const mainLabel = showDataTime ? "数据更新" : label;

  const tipParts: string[] = [];
  if (showDataTime) tipParts.push(`数据采集于 ${dayjs(dataMs).format("YYYY-MM-DD HH:mm")}`);
  if (dataDate) tipParts.push(`数据日期 ${dataDate}`);
  if (updatedAt) tipParts.push(`页面加载于 ${dayjs(updatedAt).format("HH:mm:ss")}`);
  const tooltip = `${tipParts.length ? tipParts.join(" · ") + " · " : ""}点击刷新本页数据`;

  return (
    <Tooltip title={tooltip}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
        <Tag bordered={false} style={{ fontSize: 11, marginInlineEnd: 0 }}>
          {mainLabel} <span className="num">{mainTime}</span>
        </Tag>
        <Button
          size="small"
          type="text"
          aria-label="刷新本页数据"
          icon={<ReloadOutlined spin={fetching} />}
          onClick={() => {
            queryKeys.forEach((k) => queryClient.invalidateQueries({ queryKey: k }));
            if (feeds?.length) health.refetch();
          }}
        />
      </span>
    </Tooltip>
  );
}
