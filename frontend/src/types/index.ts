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

// ---- Phase 2: derivatives (股指期权 T型报价) ----
export interface OptionLeg {
  contract_code: string;
  last: number | null;
  updown: number | null;
  volume: number | null;
  oi: number | null;
}

export interface OptionBoardRow {
  strike: number;
  call: OptionLeg | null;
  put: OptionLeg | null;
}

export interface OptionBoard {
  underlying: string;
  variety?: string | null;
  month: string | null;
  months: string[];
  trade_date: string | null;
  spot: number | null;
  atm_strike: number | null;
  rows: OptionBoardRow[];
  totals: {
    call_oi?: number | null;
    put_oi?: number | null;
    call_volume?: number | null;
    put_volume?: number | null;
    pcr_oi?: number | null;
    pcr_volume?: number | null;
    contracts?: number | null;
  };
}

export interface OptionOverviewRow {
  underlying: string;
  variety: string;
  underlying_code: string;
  trade_date: string | null;
  month: string | null;
  spot: number | null;
  atm_strike: number | null;
  pcr_oi: number | null;
  pcr_volume: number | null;
  call_oi: number | null;
  put_oi: number | null;
}

export interface OptionsPayload {
  underlyings: string[];
  board: OptionBoard;
  overview: OptionOverviewRow[];
}

// ---- Phase 2: 资金流向 (capital flow) ----
export interface NorthboundLatest {
  trade_date: string;
  board: string;
  type: string | null;
  direction: string | null;
  net_inflow: number | null;
  net_buy: number | null;
  balance: number | null;
  up: number | null;
  flat: number | null;
  down: number | null;
  index: string | null;
  index_pct: number | null;
}

export interface NorthboundPayload {
  dates: string[];
  boards: string[];
  net_inflow: Record<string, (number | null)[]>;
  up: Record<string, (number | null)[]>;
  down: Record<string, (number | null)[]>;
  latest: NorthboundLatest[];
  ref: string | null;
}

export interface MarginSnapshot {
  trade_date: string;
  rzye: number | null;
  rzmre: number | null;
  rqye: number | null;
  rzrqye: number | null;
}

export interface MarginPayload {
  dates: string[];
  sse: {
    rzye: (number | null)[];
    rzmre: (number | null)[];
    rqye: (number | null)[];
    rzrqye: (number | null)[];
  };
  szse: MarginSnapshot | null;
  latest: MarginSnapshot | null;
}

export interface LhbRow {
  code: string;
  name: string | null;
  reason: string | null;
  close: number | null;
  change_pct: number | null;
  buy_amt: number | null;
  sell_amt: number | null;
  net_amt: number | null;
  turnover: number | null;
}

export interface FlowSummary {
  northbound_date: string | null;
  north_up: number | null;
  north_down: number | null;
  southbound_net: number | null;
  southbound_net_buy: number | null;
  margin_sse: MarginSnapshot | null;
  margin_szse: MarginSnapshot | null;
  lhb_date: string | null;
  lhb_net_total: number | null;
}

// ---- Phase 2: 评级信号 (rating signals) ----
export interface SignalRow {
  id: number;
  code: string;
  name: string | null;
  trade_date: string;
  kind: "upgrade" | "downgrade" | "first" | "consensus" | string;
  direction: string | null;
  strength: string | null;
  score: number | null;
  reason: string | null;
  industry_group: string | null;
  sources?: unknown;
}

export interface SignalSummary {
  ref: string | null;
  days: number;
  counts: Record<string, number>;
  total?: number;
  industries: { industry: string; count: number }[];
}

// ---- Phase 2: 评级胜率 (rating win-rate) ----
export interface AccuracyRow {
  rank: number;
  subject: string;
  hits: number;
  total: number;
  hit_rate: number | null;
  net_skill: number | null;
  prev_delta: number | null;
}

export interface AccuracyPayload {
  ref: string | null;
  horizon: number;
  by: string;
  min_events: number;
  rows: AccuracyRow[];
  summary: {
    subjects?: number;
    events?: number;
    hits?: number;
    hit_rate?: number | null;
    net_skill?: number | null;
  };
}

// ---- Phase 2: 周统计 (weekly statistics) ----
export interface WeeklyWeek {
  week_key: string;
  orgs: number;
  reports: number;
}

export interface WeeklyMatrixRow {
  org: string;
  total: number;
  by_group: Record<string, number>;
}

export interface WeeklyMatrix {
  week_key: string | null;
  weeks: WeeklyWeek[];
  groups: string[];
  group_totals: Record<string, number>;
  orgs: WeeklyMatrixRow[];
}

export interface PeerRow {
  id: number;
  kind: string;
  industry_group: string | null;
  source: string | null;
  title: string;
  covered_by_us: boolean | null;
  url: string | null;
  uploaded_by: string | null;
}

export interface PeerPayload {
  period_key: string | null;
  periods: string[];
  rows: PeerRow[];
}

// ---- Phase 2: 全市场速览 (quant matrix) ----
export interface QuantMatrixRow {
  code: string;
  name: string;
  close: number | null;
  ma20: number | null;
  rsi12: number | null;
  trend: string;
  macd: string;
  rsi: string;
}

// ---- Phase 2: 板块/指数联动 (linkage) ----
export interface LinkagePair {
  a: string;
  a_name: string;
  b: string;
  b_name: string;
  corr: number;
}

export interface LinkageMatrix {
  ref: string | null;
  window: number;
  samples?: number;
  codes: string[];
  names: string[];
  matrix: (number | null)[][];
  pairs: LinkagePair[];
}

export interface BetaRow {
  code: string;
  name: string;
  beta: number;
  corr: number;
  r2: number;
  vol: number;
  samples: number;
}

export interface BetaPayload {
  ref: string | null;
  benchmark: string;
  benchmark_name?: string;
  window: number;
  rows: BetaRow[];
}

// ---- Phase 2: 资讯舆情 (news flash) ----
export interface NewsRelatedStock {
  code: string;
  name: string;
}

export interface NewsItem {
  id: number;
  source: "em" | "cls" | string;
  title: string;
  content: string;
  url: string | null;
  publish_date: string;
  publish_at: string; // "YYYY-MM-DD HH:mm:ss"
  sentiment: "利好" | "中性" | "利空" | null;
  sentiment_score: number | null;
  related_codes: NewsRelatedStock[];
}

export interface NewsSummary {
  ref: string | null;
  days: number;
  total: number;
  by_sentiment: Partial<Record<"利好" | "中性" | "利空", number>>;
  by_date: { date: string; total: number; 利好?: number; 中性?: number; 利空?: number }[];
}

// ---- Phase 2: 运营数据 / 管理设置 (ops & admin) ----
export interface FreshnessRow {
  feed: string;
  last_success_at: string | null;
  latest_data_date: string | null;
  rows_total: number;
  weeks_behind: number | null;
  note: string | null;
}

export interface IngestionRow {
  id: number;
  feed: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  rows_seen: number | null;
  rows_upserted: number | null;
  latency_ms: number | null;
  error: string | null;
}

export interface FeedInfo {
  name: string;
  description: string;
  per_symbol: boolean;
}

export interface AdminConfig {
  app: string;
  env: string;
  universe: string;
  universes: string[];
  auth_enabled: boolean;
  feature_ai: boolean;
  akshare: { timeout: number; max_retries: number; throttle_seconds: number };
  scheduler: {
    enabled: boolean;
    running: boolean;
    cron: string;
    timezone: string;
    next_run_at: string | null;
  };
  database: { kind: string; url: string };
}
