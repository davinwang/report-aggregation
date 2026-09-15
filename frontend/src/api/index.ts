// Typed API functions grouped by backend module. All read endpoints unwrap { data, meta }.
import { getEnvelope, getData, http } from "./client";
import type {
  BasisPayload,
  Dashboard,
  FinancialIndicatorRow,
  FlowSummary,
  HealthDeep,
  LhbRow,
  MarginPayload,
  NorthboundPayload,
  OptionsPayload,
  Paged,
  QuantSeries,
  ReportBrief,
  SecurityMeta,
  StockDetail,
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
  getData<Record<string, unknown>[]>("/api/quant/matrix", params);

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

// ---- health / ops ----
export const getHealthDeep = () => http.get<HealthDeep>("/health/deep").then((r) => r.data);
export const getOpsFreshness = () => getData<Record<string, unknown>[]>("/api/ops/freshness");
export const getOpsIngestions = (limit = 50) => getData<Record<string, unknown>[]>("/api/ops/ingestions", { limit });
export const getOpsFeeds = () => getData<{ name: string; description: string; per_symbol: boolean }[]>("/api/ops/feeds");
export const triggerIngest = (scope = "all", universe?: string) =>
  http.post("/api/ops/ingest", null, { params: { scope, universe } }).then((r) => r.data);

// ---- auth (login feature disabled; identity is hardcoded in authStore) ----
export const getMe = () =>
  getData<{ authenticated: boolean; user?: { username: string; role: string } }>("/api/me");
