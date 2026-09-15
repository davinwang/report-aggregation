// Shared TypeScript types mirroring the backend API payloads.

export interface Envelope<T> {
  data: T;
  meta: Record<string, unknown>;
}

export interface Paged<T> {
  data: T[];
  meta: { total: number; page: number; size: number; pages: number; [k: string]: unknown };
}

export type SecurityType = "stock" | "index" | "future" | "option";

export interface SecurityMeta {
  code: string;
  name: string;
  type: SecurityType;
  exchange?: string;
  industry_sw?: string | null;
  industry_group?: string | null;
}

export interface IndexQuote {
  code: string;
  name: string;
  close: number | null;
  change_pct: number | null;
  volume: number | null;
  trade_date: string;
}

export interface SectorHeat {
  name: string;
  group: string | null;
  change_pct: number | null;
  turnover: number | null;
  company_count: number | null;
}

export interface RatingSummary {
  total: number;
  by_rating: Record<string, number>;
  orgs: number;
}

export interface SignalItem {
  code: string;
  name: string | null;
  direction: string | null;
  strength: string | null;
  reason: string | null;
  trade_date: string;
  industry_group?: string | null;
}

export interface ReportBrief {
  id: number;
  code: string;
  name: string | null;
  title: string;
  org: string | null;
  analysts: string | null;
  rating: string | null;
  rating_change: string | null;
  target_price_low: number | null;
  target_price_high: number | null;
  industry: string | null;
  industry_group: string | null;
  publish_date: string | null;
  pdf_url: string | null;
  source: string;
}

export interface Dashboard {
  window: { start: string; end: string; label: string; week_key: string };
  indices: IndexQuote[];
  sectorHeatmap: SectorHeat[];
  ratingSummary: RatingSummary;
  topUpgrades: SignalItem[];
  topDowngrades: SignalItem[];
  latestReports: ReportBrief[];
  freshness: Record<string, Freshness>;
  latestTradeDate: string;
}

export interface Freshness {
  last_success_at: string | null;
  latest_data_date: string | null;
  rows_total: number;
  weeks_behind: number | null;
}

export interface QuantSeries {
  code: string;
  dates: string[];
  candle: [number | null, number | null, number | null, number | null][]; // [open, close, low, high]
  volume: (number | null)[];
  indicators: Record<string, Record<string, (number | null)[]>>;
}

export interface FinancialIndicatorRow {
  report_period: string;
  eps: number | null;
  bps: number | null;
  roe: number | null;
  roa: number | null;
  revenue_yoy: number | null;
  net_profit_yoy: number | null;
  gross_margin: number | null;
  net_margin: number | null;
  debt_ratio: number | null;
  ocfps: number | null;
}

export interface StockDetail {
  security: SecurityMeta;
  quote: {
    close: number | null;
    change_pct: number | null;
    open: number | null;
    high: number | null;
    low: number | null;
    volume: number | null;
    amount: number | null;
    turnover_rate: number | null;
    trade_date: string | null;
  } | null;
  financials: FinancialIndicatorRow | null;
  reports: ReportBrief[];
  report_total: number;
  ratings: Array<{
    trade_date: string;
    org: string | null;
    analyst: string | null;
    rating: string | null;
    rating_change: string | null;
    target_low: number | null;
    target_high: number | null;
  }>;
}

export interface HealthDeep {
  status: string;
  app: string;
  env: string;
  universe: string;
  checks: Record<string, Record<string, unknown>>;
  freshness: Record<string, Freshness>;
}

// ---- Phase 2: derivatives (股指期货基差) ----
export interface BasisContract {
  symbol: string;
  expiry: string | null;
  days_to_expiry: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  settle: number | null;
  pre_settle: number | null;
  volume: number | null;
  oi: number | null;
  basis: number | null;
  basis_annualized: number | null;
  underlying_index_close: number | null;
}

export interface BasisOverviewRow {
  variety: string;
  underlying_code: string;
  underlying_name: string;
  trade_date: string | null;
  spot: number | null;
  symbol: string | null;
  basis: number | null;
  basis_annualized: number | null;
  oi: number | null;
  volume: number | null;
  days_to_expiry: number | null;
  state: string | null;
}

export interface BasisPayload {
  varieties: string[];
  variety: string;
  underlying: { code: string; name: string };
  termStructure: { trade_date: string | null; spot: number | null; contracts: BasisContract[] };
  history: {
    dates: string[];
    basis: (number | null)[];
    basis_annualized: (number | null)[];
    spot: (number | null)[];
    symbols: string[];
  };
  overview: BasisOverviewRow[];
}
