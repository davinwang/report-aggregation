// Application shell — Bloomberg-terminal chrome: black header with amber brand
// strip + command search, scrolling ticker tape, dense dark sidebar + content.
import { useMemo } from "react";
import { Layout, Menu, Button, Space, Tooltip, Badge } from "antd";
import type { MenuProps } from "antd";
import {
  DashboardOutlined,
  AppstoreOutlined,
  ReadOutlined,
  BulbOutlined,
  AimOutlined,
  BarChartOutlined,
  LineChartOutlined,
  TableOutlined,
  SwapOutlined,
  FundOutlined,
  AccountBookOutlined,
  MoneyCollectOutlined,
  DeploymentUnitOutlined,
  RobotOutlined,
  CloudUploadOutlined,
  ControlOutlined,
  SettingOutlined,
  ReloadOutlined,
  MoonOutlined,
  SunOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import PeriodSelector from "@/components/PeriodSelector";
import SectorFilter from "@/components/SectorFilter";
import SecuritySearch from "@/components/SecuritySearch";
import TickerTape from "@/components/TickerTape";
import { useSSE } from "@/hooks/useSSE";
import { useUIStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import { MONO_FONT } from "@/styles/theme";

const { Header, Sider, Content } = Layout;

type MenuItem = Required<MenuProps>["items"][number];

const MENU: MenuItem[] = [
  {
    type: "group",
    label: "数据看板",
    children: [
      { key: "/market", icon: <DashboardOutlined />, label: "市场看板" },
      { key: "/overview", icon: <AppstoreOutlined />, label: "功能导航" },
    ],
  },
  {
    type: "group",
    label: "研报中心",
    children: [
      { key: "/research", icon: <ReadOutlined />, label: "研报库" },
      { key: "/signals", icon: <BulbOutlined />, label: "可操作信号" },
      { key: "/accuracy", icon: <AimOutlined />, label: "研报准确率" },
      { key: "/weekly", icon: <BarChartOutlined />, label: "周统计" },
    ],
  },
  {
    type: "group",
    label: "行情与技术",
    children: [
      { key: "/technical", icon: <LineChartOutlined />, label: "技术指标" },
      { key: "/market-overview", icon: <TableOutlined />, label: "全市场速览" },
    ],
  },
  {
    type: "group",
    label: "衍生品",
    children: [
      { key: "/basis", icon: <SwapOutlined />, label: "股指期货基差" },
      { key: "/options", icon: <FundOutlined />, label: "股指期权" },
    ],
  },
  {
    type: "group",
    label: "财务与资金",
    children: [
      { key: "/financials", icon: <AccountBookOutlined />, label: "财务数据" },
      { key: "/flow", icon: <MoneyCollectOutlined />, label: "资金流向" },
      { key: "/linkage", icon: <DeploymentUnitOutlined />, label: "板块联动" },
    ],
  },
  {
    type: "group",
    label: "工具",
    children: [
      { key: "/chat", icon: <RobotOutlined />, label: "AI助手" },
      { key: "/contrib", icon: <CloudUploadOutlined />, label: "上传研报" },
      { key: "/ops", icon: <ControlOutlined />, label: "运营数据" },
      { key: "/admin", icon: <SettingOutlined />, label: "管理设置" },
    ],
  },
];

const ALL_KEYS = [
  "/market", "/overview", "/research", "/signals", "/accuracy", "/weekly",
  "/technical", "/market-overview", "/basis", "/options", "/financials",
  "/flow", "/linkage", "/chat", "/contrib", "/ops", "/admin",
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { mode, toggleMode, collapsed, setCollapsed } = useUIStore();
  const user = useAuthStore((s) => s.user);

  // Live channel: refresh cached queries whenever an ingestion run finishes.
  const { status } = useSSE((evt) => {
    if (evt.event === "ingest:end") queryClient.invalidateQueries();
  });

  const selectedKey = useMemo(() => {
    const path = location.pathname;
    const match = ALL_KEYS.filter((k) => path === k || path.startsWith(k + "/")).sort(
      (a, b) => b.length - a.length,
    )[0];
    return match ?? "/market";
  }, [location.pathname]);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "0 14px",
          background: "var(--srp-bg)",
          borderBottom: "2px solid var(--srp-brand)",
          position: "sticky",
          top: 0,
          zIndex: 20,
        }}
      >
        <div
          style={{ display: "flex", alignItems: "center", gap: 9, cursor: "pointer", flex: "none" }}
          onClick={() => navigate("/market")}
        >
          <div
            style={{
              width: 22,
              height: 22,
              background: "var(--srp-brand)",
              color: "#000",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: MONO_FONT,
              fontWeight: 700,
              fontSize: 13,
            }}
          >
            S
          </div>
          <div style={{ lineHeight: 1.15 }}>
            <div style={{ fontSize: 14, fontWeight: 600, whiteSpace: "nowrap", color: "var(--srp-text)" }}>
              股票研报聚合平台
            </div>
            <div
              className="num"
              style={{ fontSize: 9, letterSpacing: "0.22em", color: "var(--srp-brand)", whiteSpace: "nowrap" }}
            >
              SRP TERMINAL
            </div>
          </div>
        </div>

        <SecuritySearch />

        <div style={{ flex: 1 }} />

        <Space size={6}>
          <PeriodSelector />
          <SectorFilter />
          <Tooltip title="刷新数据 (重新拉取)">
            <Button size="small" icon={<ReloadOutlined />} onClick={() => queryClient.invalidateQueries()} />
          </Tooltip>
          <Tooltip title={`SSE: ${status}`}>
            <Badge
              status={status === "open" ? "processing" : status === "error" ? "error" : "default"}
              text={
                <span className="num" style={{ fontSize: 10, letterSpacing: "0.12em" }}>
                  LIVE
                </span>
              }
            />
          </Tooltip>
          <Tooltip title="切换主题">
            <Button size="small" icon={mode === "light" ? <MoonOutlined /> : <SunOutlined />} onClick={toggleMode} />
          </Tooltip>
          <span
            className="num"
            style={{
              fontSize: 11,
              color: "var(--srp-brand)",
              border: "1px solid var(--srp-brand)",
              padding: "1px 8px",
              whiteSpace: "nowrap",
            }}
          >
            {user?.username ?? "admin"}
          </span>
        </Space>
      </Header>

      <TickerTape />

      <Layout>
        <Sider
          width={208}
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          theme={mode === "dark" ? "dark" : "light"}
          style={{ borderRight: "1px solid var(--srp-border)" }}
        >
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={MENU}
            onClick={({ key }) => navigate(key)}
            style={{ borderInlineEnd: "none", height: "100%", overflowY: "auto", background: "transparent" }}
          />
        </Sider>
        <Content style={{ background: "var(--srp-bg)", minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
