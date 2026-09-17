// Per-page data freshness + refresh control (replaces the old global header
// refresh button): shows when THIS page's queries last got data and a button
// that refetches only this page's queries.
//
// Tracks the newest `dataUpdatedAt` across the given query-key prefixes by
// subscribing to the react-query cache — no prop plumbing per fetch, and the
// spinner reflects any in-flight refetch (SSE-driven included).
import { useEffect, useState } from "react";
import { Button, Tag, Tooltip } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useQueryClient } from "@tanstack/react-query";
import type { QueryKey } from "@tanstack/react-query";
import dayjs from "dayjs";

interface Props {
  /** Query-key prefixes considered "this page", e.g. [["market"], ["flow"]]. */
  queryKeys: QueryKey[];
  /** Label prefix, defaults to 更新. */
  label?: string;
}

function keyMatches(key: QueryKey, prefixes: QueryKey[]): boolean {
  return prefixes.some((prefix) =>
    (prefix as readonly unknown[]).every((v, i) => (key as readonly unknown[])[i] === v),
  );
}

export default function PageRefresh({ queryKeys, label = "更新" }: Props) {
  const queryClient = useQueryClient();
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [fetching, setFetching] = useState(false);

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

  const time = updatedAt ? dayjs(updatedAt).format("HH:mm:ss") : "-";

  return (
    <Tooltip title={`本页数据${label}于 ${time} · 点击刷新本页数据`}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
        <Tag bordered={false} style={{ fontSize: 11, marginInlineEnd: 0 }}>
          {label} <span className="num">{time}</span>
        </Tag>
        <Button
          size="small"
          type="text"
          aria-label="刷新本页数据"
          icon={<ReloadOutlined spin={fetching} />}
          onClick={() =>
            queryKeys.forEach((k) => queryClient.invalidateQueries({ queryKey: k }))
          }
        />
      </span>
    </Tooltip>
  );
}
