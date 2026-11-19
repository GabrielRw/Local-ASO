// Shapes for /api/pricing (src/local_aso_tracker/services/pricing.py).

export type PricedItemKind = "app" | "iap" | "subscription";

export interface PricedItem {
  kind: PricedItemKind;
  id: string;
  name: string;
  productId: string;
}

export interface PriceRow {
  territory: string;
  currency: string;
  currentPrice: number;
  currentPointId: string;
  manual: boolean;
  equalizedPrice: number;
  pppRatio: number | null;
  ratio: number | null;
  suggestedPrice: number | null;
  suggestedPointId: string | null;
  changePercent: number | null;
}

export interface PriceSuggestions {
  kind: PricedItemKind;
  id: string;
  baseTerritory: string;
  basePrice: number;
  baseCurrency: string;
  floor: number;
  ceiling: number;
  scope: "tracked" | "all";
  rows: PriceRow[];
}

export interface PriceEvent {
  itemType: PricedItemKind;
  itemName: string;
  territory: string;
  currency: string;
  beforePrice: string | null;
  afterPrice: string;
  status: "success" | "failed" | string;
  error: string | null;
  createdAt: string;
}

export interface PricingData {
  appId: number;
  ppp: { source: string; sourceUrl: string; retrieved: string; indicator: string; countries: number; latestYear: number | null };
  defaults: { floor: number; ceiling: number };
  trackedTerritories: string[];
  events: PriceEvent[];
}

export interface PricePushResult {
  results: { territory: string; error: string | null }[];
}
