// Typed API functions grouped by backend module. All read endpoints unwrap { data, meta }.
import { getEnvelope, getData, http } from "./client";
import type {
  AccuracyPayload,
  AdminConfig,
  BasisPayload,
  BetaPayload,
  Dashboard,
  FeedInfo,
  FinancialIndicatorRow,
  FlowSummary,
  Freshness,
  FreshnessRow,
  HealthDeep,
  IngestionRow,
  LhbRow,
  LinkageMatrix,
  MarginPayload,
  NewsItem,
  NewsSummary,
  NorthboundPayload,
  OptionsPayload,
  Paged,
  PeerPayload,
  QuantMatrixRow,
  QuantSeries,
  ReportBrief,
  SecurityMeta,
  SignalRow,
  SignalSummary,
  StockDetail,
  WeeklyMatrix,
} from "@/types";

// ---- meta ----
export const getSecurities = (params?: { keyword?: string; type?: string; limit?: number }) =>
  getData<SecurityMeta[]>("/api/meta/securities", params);
export const getIndustries = () =>
  getData<{ groups: string[]; group_of: Record<string, string>; boards: { name: string; group: string | null }[] }>(
    "/api/meta/industries",
  );
export const getDates = () =>
  getData<{ latest_trade_date: string | null; periods: { key: string; label: string }[] }>("/api/meta/dates");
export const getIndicatorAliases = () =>
  getData<{ indicators: string[]; aliases: Record<string, string> }>("/api/meta/indicator-aliases");

// ---- market dashboard ----
export const getDashboard = (params: { period?: string; date?: string; sector?: string | null }) =>
  getData<Dashboard>("/api/market/dashboard", params as Record<string, unknown>);

// ---- research ----
export interface ReportQuery {
  keyword?: string;
  org?: string;
  industry?: string;
  rating?: string;
  code?: string;
  start?: string;
  end?: string;
  page?: number;
  size?: number;
  sort?: string;
}
export const getReports = (params: ReportQuery) =>
  getEnvelope<Paged<ReportBrief>["data"]>("/api/research/reports", params as Record<string, unknown>).then((r) => ({
    rows: r.data,
    meta: r.meta as Paged<ReportBrief>["meta"],
  }));
export const getResearchFacets = () =>
  getData<{ orgs: string[]; industries: string[]; ratings: string[] }>("/api/research/facets");
export const getOrgs = () => getData<{ org: string; count: number }[]>("/api/research/orgs");

// ---- quant / technical ----
export const getSeries = (params: { code: string; indicators?: string; period?: string; freq?: string; adjust?: string }) =>
  getData<QuantSeries>("/api/quant/series", params as Record<string, unknown>);
export const getMatrix = (params?: { limit?: number; scope?: string }) =>
  getData<QuantMatrixRow[]>("/api/quant/matrix", params);

// ---- financials ----
export const getStatements = (code: string, type: string, source = "em", limit = 12) =>
  getData<{ report_period: string; source: string; data: Record<string, unknown> }[]>(
    `/api/financials/${code}/statements`,
    { type, source, limit },
  );
export const getFinancialIndicators = (code: string, limit = 16) =>
  getData<FinancialIndicatorRow[]>(`/api/financials/${code}/indicators`, { limit });
export const getEarnings = (code: string, limit = 12) =>
  getData<Record<string, unknown>[]>(`/api/financials/${code}/earnings`, { limit });
export const getDisclosures = (code: string, params?: { category?: string; page?: number; size?: number }) =>
  getEnvelope<Record<string, unknown>[]>(`/api/financials/${code}/disclosures`, params as Record<string, unknown>);

// ---- stock detail ----
export const getStockDetail = (code: string) => getData<StockDetail>(`/api/stock/${code}`);
export const getStockReports = (code: string, page = 1, size = 20) =>
  getEnvelope<ReportBrief[]>(`/api/stock/${code}/reports`, { page, size });
export const getStockFlow = (code: string, limit = 30) =>
  getData<Record<string, unknown>[]>(`/api/stock/${code}/flow`, { limit });

// ---- derivatives (衍生品) ----
export const getFuturesBasis = (params?: { variety?: string; days?: number; date?: string }) =>
  getData<BasisPayload>("/api/derivatives/futures/basis", params as Record<string, unknown>);
export const getOptionsBoard = (params?: { underlying?: string; month?: string; date?: string }) =>
  getData<OptionsPayload>("/api/derivatives/options/board", params as Record<string, unknown>);

// ---- flow (资金流向) ----
export const getFlowSummary = () => getData<FlowSummary>("/api/flow/summary");
export const getNorthbound = (days = 30) => getData<NorthboundPayload>("/api/flow/northbound", { days });
export const getMargin = (days = 60) => getData<MarginPayload>("/api/flow/margin", { days });
export const getLhb = (params?: { date?: string; direction?: "buy" | "sell"; page?: number; size?: number }) =>
  getEnvelope<LhbRow[]>("/api/flow/lhb", params as Record<string, unknown>).then((r) => ({
    rows: r.data,
    meta: r.meta as Paged<LhbRow>["meta"] & { trade_date?: string | null; stats?: { net_total?: number | null } },
  }));

// ---- news (资讯舆情) ----
export const getNews = (params?: {
  q?: string;
  sentiment?: string;
  source?: string;
  start?: string;
  end?: string;
  page?: number;
  size?: number;
}) =>
  getEnvelope<NewsItem[]>("/api/news", params as Record<string, unknown>).then((r) => ({
    rows: r.data,
    meta: r.meta as Paged<NewsItem>["meta"],
  }));
export const getNewsSummary = (days = 1) =>
  getEnvelope<NewsSummary>("/api/news/summary", { days }).then((r) => ({
    data: r.data,
    freshness: (r.meta as { freshness?: Freshness | null }).freshness ?? null,
  }));

// ---- signals (评级信号) ----
export const getSignals = (params?: {
  action?: string;
  industry?: string;
  days?: number;
  date?: string;
  page?: number;
  size?: number;
}) =>
  getEnvelope<SignalRow[]>("/api/signals", params as Record<string, unknown>).then((r) => ({
    rows: r.data,
    meta: r.meta as Paged<SignalRow>["meta"] & { ref?: string | null; days?: number },
  }));
export const getSignalSummary = (days = 30) => getData<SignalSummary>("/api/signals/summary", { days });
export const refreshSignals = (lookbackDays = 180) =>
  http.post("/api/signals/refresh", null, { params: { lookback_days: lookbackDays } }).then((r) => r.data);

// ---- accuracy (评级胜率) ----
export const getAccuracyLeaderboard = (params?: {
  horizon?: number;
  by?: "org" | "analyst";
  min_events?: number;
  limit?: number;
}) => getData<AccuracyPayload>("/api/accuracy/leaderboard", params as Record<string, unknown>);
export const refreshAccuracy = (lookbackDays = 180) =>
  http.post("/api/accuracy/refresh", null, { params: { lookback_days: lookbackDays } }).then((r) => r.data);

// ---- weekly (周统计) ----
export const getWeeklyMatrix = (week?: string) =>
  getData<WeeklyMatrix>("/api/weekly/matrix", week ? { week } : undefined);
export const getWeeklyPeer = (period?: string) =>
  getData<PeerPayload>("/api/weekly/peer", period ? { period } : undefined);
export const refreshWeekly = (weeksBack = 12) =>
  http.post("/api/weekly/refresh", null, { params: { weeks_back: weeksBack } }).then((r) => r.data);

// ---- linkage (板块/指数联动) ----
export const getLinkageMatrix = (window = 120) =>
  getData<LinkageMatrix>("/api/linkage/matrix", { window });
export const getLinkageBeta = (params?: { window?: number; benchmark?: string; limit?: number }) =>
  getData<BetaPayload>("/api/linkage/beta", params as Record<string, unknown>);

// ---- health / ops ----
export const getHealthDeep = () => http.get<HealthDeep>("/health/deep").then((r) => r.data);
export const getOpsFreshness = () => getData<FreshnessRow[]>("/api/ops/freshness");
export const getOpsIngestions = (limit = 50) => getData<IngestionRow[]>("/api/ops/ingestions", { limit });
export const getOpsFeeds = () => getData<FeedInfo[]>("/api/ops/feeds");
export const triggerIngest = (scope = "all", universe?: string) =>
  http.post("/api/ops/ingest", null, { params: { scope, universe } }).then((r) => r.data);

// ---- admin (管理设置) ----
export const getAdminConfig = () => getData<AdminConfig>("/api/admin/config");
export const adminTriggerIngest = (scope = "all", universe?: string) =>
  http.post("/api/admin/ingest", null, { params: { scope, universe } }).then((r) => r.data);

// ---- auth (login feature disabled; identity is hardcoded in authStore) ----
export const getMe = () =>
  getData<{ authenticated: boolean; user?: { username: string; role: string } }>("/api/me");
