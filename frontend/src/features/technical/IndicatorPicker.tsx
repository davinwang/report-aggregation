// 指标选择器 — drives which indicators the chart fetches, which ride the price grid and
// which get their own sub-pane. Built from the backend's indicator catalog so the picker
// can never list something the engine doesn't compute (and can't hide something it does).
import { useMemo } from "react";
import { Badge, Popover, Space, Tag, Tooltip, Typography } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import type { IndicatorMeta } from "@/types";
import { MAX_SUB_PANES, VOLUME_PANE } from "@/components/KLineChart";

interface Props {
  catalog: IndicatorMeta[];
  overlays: string[];
  subs: string[];
  onOverlays: (next: string[]) => void;
  onSubs: (next: string[]) => void;
  loading?: boolean;
}

export default function IndicatorPicker({ catalog, overlays, subs, onOverlays, onSubs, loading }: Props) {
  const byGroup = useMemo(() => {
    const groups = new Map<string, IndicatorMeta[]>();
    catalog.forEach((item) => {
      const list = groups.get(item.group) ?? [];
      list.push(item);
      groups.set(item.group, list);
    });
    return [...groups.entries()];
  }, [catalog]);

  const paneKeys = useMemo(
    () => [...overlays, ...subs.filter((k) => k !== VOLUME_PANE)],
    [overlays, subs],
  );

  const toggle = (key: string, pane: "main" | "sub") => {
    const isOn = paneKeys.includes(key);
    if (isOn) {
      onOverlays(overlays.filter((k) => k !== key));
      onSubs(subs.filter((k) => k !== key));
      return;
    }
    if (pane === "main") {
      onOverlays([...overlays, key]);
      return;
    }
    // Sub-panes get a hard cap: each one is a grid with its own axis, and past ~4 the
    // price grid stops being readable, so the cap is a layout constraint, not a quota.
    if (subs.filter((k) => k !== VOLUME_PANE).length >= MAX_SUB_PANES) return;
    onSubs([...subs.filter((k) => k !== VOLUME_PANE), key, VOLUME_PANE]);
  };

  return (
    <Space wrap size={[6, 8]}>
      {byGroup.map(([group, items]) => (
        <Space key={group} size={4} wrap>
          <Typography.Text className="muted" style={{ fontSize: 11 }}>
            {group}
          </Typography.Text>
          {items.map((item) => {
            const pane = overlays.includes(item.key) ? "main" : subs.includes(item.key) ? "sub" : null;
            // antd's CheckableTag has no `disabled`; suppress the click instead, so the
            // tag keeps its tooltip (which explains what the indicator is) while loading.
            const atCap = !pane && item.pane === "sub"
              && subs.filter((k) => k !== VOLUME_PANE).length >= MAX_SUB_PANES;
            return (
              <Tooltip key={item.key} title={<IndicatorTip meta={item} pane={pane} atCap={atCap} />}>
                <Badge
                  count={pane === "sub" ? subs.filter((k) => k !== VOLUME_PANE).length : 0}
                  showZero={false}
                  size="small"
                  offset={[-2, 2]}
                >
                  <Tag.CheckableTag
                    checked={pane !== null}
                    onChange={() => !loading && !atCap && toggle(item.key, item.pane === "main" ? "main" : "sub")}
                    style={{
                      marginInlineEnd: 0,
                      cursor: loading || atCap ? "not-allowed" : "pointer",
                      opacity: atCap ? 0.4 : 1,
                    }}
                  >
                    {pane === "main" ? "主" : pane === "sub" ? "副" : null} {item.label}
                  </Tag.CheckableTag>
                </Badge>
              </Tooltip>
            );
          })}
        </Space>
      ))}
      <Popover
        placement="bottomLeft"
        title="主图 / 副图"
        content={
          <div style={{ maxWidth: 260 }}>
            <Typography.Paragraph style={{ marginBottom: 6 }}>
              <b>主图</b> 画在 K 线上（均线、布林带、VWAP、SAR、唐奇安…）。
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 6 }}>
              <b>副图</b> 各自占一个独立坐标系（MACD、KDJ、RSI…）。
              同一坐标系里混放不同量纲的指标（MACD 的 0 轴和 RSI 的 30/70）会让读数失真，
              所以最多同时开 {MAX_SUB_PANES} 个副图。
            </Typography.Paragraph>
            <Typography.Text type="secondary">
              标签左侧的「主」「副」表示当前放置位置。
            </Typography.Text>
          </div>
        }
      >
        <QuestionCircleOutlined className="muted" style={{ cursor: "help" }} />
      </Popover>
    </Space>
  );
}

function IndicatorTip({ meta, pane, atCap }: { meta: IndicatorMeta; pane: string | null; atCap?: boolean }) {
  const params = Object.entries(meta.params ?? {})
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("/") : v}`)
    .join("  ");
  return (
    <div style={{ maxWidth: 280 }}>
      <div style={{ marginBottom: 4 }}>
        <b>{meta.label}</b>
        <Typography.Text type="secondary" style={{ marginLeft: 6 }}>
          {meta.key}
        </Typography.Text>
      </div>
      <div style={{ marginBottom: 4, lineHeight: 1.6 }}>{meta.desc}</div>
      {params && (
        <div className="muted" style={{ fontSize: 11 }}>
          默认参数 {params}
        </div>
      )}
      {meta.needs.length > 0 && (
        <div className="muted" style={{ fontSize: 11 }}>
          依赖字段 {meta.needs.join(" / ")}（数据源缺失时该指标不出值）
        </div>
      )}
      {pane === null && (atCap ? `副图已开满 ${MAX_SUB_PANES} 个，先关掉一个再添加` : "点击放入副图")}
    </div>
  );
}
