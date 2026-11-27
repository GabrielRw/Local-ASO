// Shapes returned by the local Python dashboard API (src/local_aso_tracker/web/server.py).
// Only fields the UI reads are typed; the server may send more.

export type Device = "iphone" | "ipad";
export type PopularityStatus = "measured" | "unavailable" | null;

export interface AppSummary {
  id: number;
  name: string;
  appleAppId: number;
  bundleId: string | null;
  artworkUrl: string | null;
  active: boolean;
}

export interface Country {
  code: string;
  name: string;
  active: boolean;
}

export interface Market {
  code: string;
  name: string;
  language: string;
}

export interface AgentInstall {
  path: string;
  version: string;
}

export interface AgentProvider {
  id: string;
  label: string;
  available: boolean;
  /** CLI that will run (the chosen copy, else the newest found). */
  path?: string | null;
  version?: string | null;
  /** Every copy of the CLI found on this Mac, newest first. */
  installs?: AgentInstall[];
  configuredPath?: string;
  canSignIn?: boolean;
}

/** POST /api/agent/check: one tiny request through the same runner audits use. */
export interface AgentCheck {
  provider: string;
  path: string | null;
  version: string | null;
  ok: boolean;
  signedIn: boolean | null;
  message: string;
}

export interface TopApp {
  position: number;
  appId: number;
  name: string;
  artworkUrl: string | null;
  averageRating: number | null;
  ratingCount: number | null;
}

export interface Ranking {
  targetId: number;
  keyword: string;
  country: string;
  device: Device;
  rank: number | null;
  found: boolean;
  resultLimit: number;
  volumeEstimate: number | null;
  popularity: number | null;
  popularityStatus: PopularityStatus;
  popularityFetchedAt: string | null;
  difficultyEstimate: number | null;
  estimateSampleSize: number | null;
  topApps: TopApp[];
  previousRank: number | null;
  previousFound: boolean | null;
  change: string;
  checkedAt: string;
  opportunity: string;
  status: string;
  error: string | null;
}

export interface HistoryPoint {
  targetId: number;
  keyword: string;
  country: string;
  device: Device;
  rank: number | null;
  found: boolean;
  resultLimit: number;
  checkedAt: string;
}

export interface MetricTrend {
  current: number | null;
  baseline: number | null;
  percent: number | null;
  better: boolean | null;
}

export type MetricTrendSet = Record<
  "tracked" | "top10" | "top50" | "notVisible" | "averageRank",
  MetricTrend
>;

export interface Listing {
  appleAppId: number;
  name: string;
  bundleId: string | null;
  seller: string | null;
  version: string | null;
  url: string | null;
  artworkUrl: string | null;
  genre: string | null;
  description: string;
  averageRating: number | null;
  ratingCount: number | null;
  updatedAt: string | null;
  releasedAt: string | null;
  languages: string[];
  fileSizeBytes: number | null;
  price: string | null;
  minimumOsVersion: string | null;
}

export interface HealthItem {
  key: string;
  label: string;
  score: number;
  maximum: number;
  detail: string;
  available: boolean;
}

export interface Health {
  score: number | null;
  label: string;
  items: HealthItem[];
  suggestions: string[];
  methodology: string;
}

export interface ListingMetadata {
  name: string;
  subtitle: string;
  keywords: string;
  channelGoal: "aso_seo_aeo" | "ugc_ads";
  brandTerm: string;
  updatedAt: string | null;
}

export interface Bootstrap {
  onboarding: { completed: boolean; shouldOpen: boolean };
  apps: AppSummary[];
  countries: Country[];
  devices: { code: Device; name: string }[];
  /** Every App Store storefront Local ASO can research, with its language. */
  markets: Market[];
  agentProviders: AgentProvider[];
  defaultAgentProvider: string;
  selectedAppId: number | null;
  selectedCountry: string;
  listingMetadata: ListingMetadata | null;
  rankings: Ranking[];
  targetCounts: Record<string, number>;
  history: HistoryPoint[];
  summary: Record<string, number | string | null>;
  metricTrends: Record<string, MetricTrendSet>;
  metricTrends30d: Record<string, MetricTrendSet>;
  methodology: string;
  estimateMethodology: { version: string; window: string; volume: string; difficulty: string };
  listing?: Listing;
  listingError?: string;
  health?: Health;
}

export interface SyncStatus {
  state: "idle" | "running" | "success" | "partial" | "error" | "disabled";
  startedAt: string | null;
  finishedAt: string | null;
  nextRunAt: string | null;
  targets: number;
  searches: number;
  failures: number;
  skipped: number;
  error: string | null;
}

// --- Audits -----------------------------------------------------------------

export type AuditStatus = "queued" | "running" | "success" | "partial" | "error" | "cancelled";

export interface AuditFinding {
  position: number;
  tone: "positive" | "info" | "warning" | "danger";
  category: string;
  title: string;
  detail: string;
  terms: string[];
}

export interface AuditKeyword {
  id: number;
  keyword: string;
  intent: string;
  rationale: string;
  rank: number | null;
  found: boolean;
  resultLimit: number;
  volume: number | null;
  difficulty: number | null;
  popularity: number | null;
  popularityStatus: PopularityStatus;
  opportunity: number | null;
  sampleSize: number;
  checkedAt: string | null;
  status: string;
  error: string | null;
}

export interface AuditPaidKeyword {
  keyword: string;
  brandOwner: string | null;
  rank: number | null;
  found: boolean;
  resultLimit: number;
  popularity: number | null;
  popularityStatus: PopularityStatus;
  status: string;
}

export interface AuditCountry {
  id: number;
  code: string;
  name: string;
  status: string;
  score: number | null;
  rankingScore: number | null;
  listingScore: number | null;
  localizationScore: number | null;
  competitionScore: number | null;
  summary: string | null;
  error: string | null;
  startedAt: string | null;
  completedAt: string | null;
  findings: AuditFinding[];
  keywords: AuditKeyword[];
  paidKeywords: AuditPaidKeyword[];
}

export interface AuditRunSummary {
  id: number;
  status: AuditStatus;
  scope: string;
  country: string;
  device: Device;
  provider: string;
  score: number | null;
  createdAt: string;
  completedAt: string | null;
}

export interface AuditRun extends AuditRunSummary {
  appId: number;
  promptVersion: string;
  startedAt: string | null;
  error: string | null;
  progress: { completed: number; total: number };
  countries: AuditCountry[];
}

export interface AuditLatest extends AuditRunSummary {
  countryName: string;
}

export interface AuditPayload {
  appId: number;
  runs: AuditRunSummary[];
  run: AuditRun | null;
  latestByCountry: AuditLatest[];
  providers: AgentProvider[];
  defaultProvider: string;
  auditLanguage: string;
  agentPaths: AgentPaths;
}

/** Saved CLI path per provider ("" = auto-detect) plus the local Ollama connection. */
export interface AgentPaths {
  claude: string;
  codex: string;
  gemini: string;
  opencode: string;
  ollama: { url: string; model: string; models: string[] };
}

/** App Store Connect API key status (the key itself never reaches the browser). */
export interface AppStoreConnectStatus {
  configured: boolean;
  ready: boolean;
  issuerId: string;
  keyId: string;
  keyPath: string;
  keyExists: boolean;
  keyModeSafe: boolean;
}
