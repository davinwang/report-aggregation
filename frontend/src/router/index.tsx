// Route tree (React Router v6). Login is disabled — a hardcoded admin identity is
// always active, so no auth guards are needed. Phase-1 pages are implemented;
// later-phase routes render ComingSoon placeholders so navigation stays complete.
import { lazy, Suspense, type ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Spin } from "antd";
import AppLayout from "@/layouts/AppLayout";
import ComingSoon from "@/features/common/ComingSoon";
import NotFound from "@/features/common/NotFound";

// Lazy Phase-1 pages (code-split).
const MarketPage = lazy(() => import("@/features/market/MarketPage"));
const ResearchPage = lazy(() => import("@/features/research/ResearchPage"));
const TechnicalPage = lazy(() => import("@/features/technical/TechnicalPage"));
const FinancialsPage = lazy(() => import("@/features/financials/FinancialsPage"));
const StockDetailPage = lazy(() => import("@/features/stock/StockDetailPage"));
const OverviewPage = lazy(() => import("@/features/overview/OverviewPage"));
const BasisPage = lazy(() => import("@/features/derivatives/BasisPage"));
const OptionsPage = lazy(() => import("@/features/derivatives/OptionsPage"));
const FlowPage = lazy(() => import("@/features/flow/FlowPage"));
const SignalsPage = lazy(() => import("@/features/signals/SignalsPage"));
const AccuracyPage = lazy(() => import("@/features/accuracy/AccuracyPage"));
const WeeklyPage = lazy(() => import("@/features/weekly/WeeklyPage"));
const MarketOverviewPage = lazy(() => import("@/features/market/MarketOverviewPage"));
const LinkagePage = lazy(() => import("@/features/linkage/LinkagePage"));

function Fallback(): ReactElement {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        justifyContent: "center",
        alignItems: "center",
        height: "60vh",
      }}
    >
      <Spin size="large" />
      <span style={{ color: "#999" }}>加载中…</span>
    </div>
  );
}

export default function AppRoutes(): ReactElement {
  return (
    <Suspense fallback={<Fallback />}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/market" replace />} />
          <Route path="/" element={<Navigate to="/market" replace />} />
          {/* Legacy /login now just returns to the dashboard (login removed). */}
          <Route path="/login" element={<Navigate to="/market" replace />} />

          {/* Phase 1 — implemented */}
          <Route path="/market" element={<MarketPage />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/research" element={<ResearchPage />} />
          <Route path="/technical" element={<TechnicalPage />} />
          <Route path="/technical/:code" element={<TechnicalPage />} />
          <Route path="/financials" element={<FinancialsPage />} />
          <Route path="/financials/:code" element={<FinancialsPage />} />
          <Route path="/stock/:code" element={<StockDetailPage />} />
          <Route path="/basis" element={<BasisPage />} />
          <Route path="/options" element={<OptionsPage />} />
          <Route path="/flow" element={<FlowPage />} />
          <Route path="/signals" element={<SignalsPage />} />
          <Route path="/accuracy" element={<AccuracyPage />} />
          <Route path="/weekly" element={<WeeklyPage />} />
          <Route path="/market-overview" element={<MarketOverviewPage />} />
          <Route path="/linkage" element={<LinkagePage />} />

          {/* Phase 2 — placeholders (navigation already wired) */}
          {/* 上传研报/审核 — deferred to Phase 3 (scope decision) */}
          <Route path="/contrib" element={<ComingSoon title="上传研报" phase={3} />} />
          <Route path="/contrib/review" element={<ComingSoon title="研报审核" phase={3} />} />
          <Route path="/ops" element={<ComingSoon title="运营数据" description="采集日志 / 新鲜度 / 错误流" />} />
          <Route path="/admin" element={<ComingSoon title="管理设置" description="universe / 调度 / 接口开关" />} />

          {/* Phase 3 — AI, flag-gated (stub) */}
          <Route path="/chat" element={<ComingSoon title="AI助手" phase={3} description="LLM 问答（后置）" />} />

          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
