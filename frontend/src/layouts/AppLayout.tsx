// Application shell — Bloomberg-terminal chrome: black header with amber brand
// strip + command search, scrolling ticker tape, dense dark sidebar + content.
import { useEffect, useMemo, useState } from "react";
import { Layout, Menu, Button, Space, Tooltip, Badge, Drawer } from "antd";
import type { MenuProps } from "antd";
import {
  HomeOutlined,
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
  NotificationOutlined,
  RobotOutlined,
  SettingOutlined,
  MoonOutlined,
  SunOutlined,
  MenuOutlined,
  CloseOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import PeriodSelector from "@/components/PeriodSelector";
import SectorFilter from "@/components/SectorFilter";
import SecuritySearch from "@/components/SecuritySearch";
import TickerTape from "@/components/TickerTape";
import { useSSE } from "@/hooks/useSSE";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useUIStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import { MONO_FONT } from "@/styles/theme";

const { Header, Sider, Content } = Layout;

type MenuItem = Required<MenuProps>["items"][number];

const MENU: MenuItem[] = [
  {
    type: "group",
    label: "首页",
    children: [{ key: "/market", icon: <HomeOutlined />, label: "市场看板" }],
  },
  {
    type: "group",
    label: "数据看板",
    children: [
      { key: "/news", icon: <NotificationOutlined />, label: "资讯舆情" },
    ],
  },
  {
    type: "group",
    label: "研报中心",
    children: [
      { key: "/research", icon: <ReadOutlined />, label: "研报库" },
      { key: "/signals", icon: <BulbOutlined />, label: "评级信号" },
      { key: "/pool", icon: <BulbOutlined />, label: "机构推荐池" },
      { key: "/accuracy", icon: <AimOutlined />, label: "评级胜率" },
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
      { key: "/admin", icon: <SettingOutlined />, label: "管理设置" },
    ],
  },
];

const ALL_KEYS = [
  "/market", "/news", "/research", "/signals", "/pool", "/accuracy", "/weekly",
  "/technical", "/market-overview", "/basis", "/options", "/financials",
  "/flow", "/linkage", "/chat", "/admin",
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { mode, toggleMode, collapsed, setCollapsed } = useUIStore();
  const user = useAuthStore((s) => s.user);
  const isMobile = useIsMobile();

  // Mobile nav drawer: the sidebar collapses into a single button; tapping it
  // opens the menu as a full-screen sheet that closes on selection.
  const [navOpen, setNavOpen] = useState(false);

  // Any route change (menu tap, ticker link, drawer backdrop) dismisses the sheet.
  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

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

  const onMenuClick: MenuProps["onClick"] = ({ key }) => {
    setNavOpen(false);
    navigate(key);
  };

  const navMenu = (
    <Menu
      mode="inline"
      selectedKeys={[selectedKey]}
      items={MENU}
      onClick={onMenuClick}
      style={{ borderInlineEnd: "none", height: "100%", overflowY: "auto", background: "transparent" }}
    />
  );

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: isMobile ? "0 10px" : "0 14px",
          background: "var(--srp-bg)",
          borderBottom: "2px solid var(--srp-brand)",
          position: "sticky",
          top: 0,
          zIndex: 20,
        }}
      >
        {isMobile && (
          <Button
            size="small"
            type="text"
            icon={<MenuOutlined />}
            aria-label="打开导航菜单"
            onClick={() => setNavOpen(true)}
            style={{ color: "var(--srp-text)", flex: "none", paddingInline: 4 }}
          />
        )}

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

        {/* Search + global filters live in the header on desktop only; on mobile
            they move inside the nav drawer to keep the header uncluttered. */}
        {!isMobile && <SecuritySearch />}

        <div style={{ flex: 1 }} />

        <Space size={6}>
          {!isMobile && (
            <>
              <PeriodSelector />
              <SectorFilter />
            </>
          )}
          {!isMobile && (
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
          )}
          <Tooltip title="切换主题">
            <Button size="small" icon={mode === "light" ? <MoonOutlined /> : <SunOutlined />} onClick={toggleMode} />
          </Tooltip>
          {!isMobile && (
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
          )}
        </Space>
      </Header>

      <TickerTape />

      <Layout>
        {!isMobile && (
          <Sider
            width={208}
            collapsible
            collapsed={collapsed}
            onCollapse={setCollapsed}
            theme={mode === "dark" ? "dark" : "light"}
            style={{ borderRight: "1px solid var(--srp-border)" }}
          >
            {navMenu}
          </Sider>
        )}
        <Content style={{ background: "var(--srp-bg)", minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>

      {/* Mobile navigation: the sidebar collapsed into a header button; tapping it
          opens this full-screen sheet, and a selection navigates + dismisses it. */}
      <Drawer
        open={isMobile && navOpen}
        onClose={() => setNavOpen(false)}
        placement="left"
        width="100vw"
        closable={false}
        rootClassName="srp-mobile-nav"
        styles={{ body: { padding: 0, background: "var(--srp-bg)" } }}
      >
        <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              padding: "8px 12px",
              borderBottom: "1px solid var(--srp-border)",
              flex: "none",
            }}
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
                flex: "none",
              }}
            >
              S
            </div>
            <div style={{ lineHeight: 1.15, flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--srp-text)" }}>股票研报聚合平台</div>
              <div className="num" style={{ fontSize: 9, letterSpacing: "0.22em", color: "var(--srp-brand)" }}>
                SRP TERMINAL
              </div>
            </div>
            <Button
              size="small"
              type="text"
              icon={<CloseOutlined />}
              aria-label="关闭导航菜单"
              onClick={() => setNavOpen(false)}
              style={{ color: "var(--srp-text)", flex: "none" }}
            />
          </div>

          {/* Global controls that live in the header on desktop. */}
          <div
            style={{
              display: "grid",
              gap: 8,
              padding: "10px 12px",
              borderBottom: "1px solid var(--srp-border)",
              flex: "none",
            }}
          >
            <SecuritySearch width="100%" />
            <div style={{ display: "flex", gap: 8 }}>
              <PeriodSelector width="38%" />
              <SectorFilter width="62%" />
            </div>
          </div>

          <div style={{ flex: 1, minHeight: 0 }}>{navMenu}</div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "8px 12px",
              borderTop: "1px solid var(--srp-border)",
              flex: "none",
            }}
          >
            <span className="num" style={{ fontSize: 11, color: "var(--srp-brand)" }}>
              {user?.username ?? "admin"}
            </span>
            <Badge
              status={status === "open" ? "processing" : status === "error" ? "error" : "default"}
              text={
                <span className="num" style={{ fontSize: 10, letterSpacing: "0.12em" }}>
                  LIVE
                </span>
              }
            />
          </div>
        </div>
      </Drawer>
    </Layout>
  );
}
