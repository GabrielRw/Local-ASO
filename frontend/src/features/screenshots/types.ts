// Shapes for /api/screenshots (src/local_aso_tracker/services/screenshots.py studio_payload).

import type { ScreenshotStyle } from "./render";

export type ScreenshotDeviceId = "iphone" | "ipad";

export interface ScreenshotDevice {
  label: string;
  displayType: string;
  width: number;
  height: number;
}

export interface ScreenshotCaption {
  headline: string;
  subline: string;
  origin: "user" | "ai" | string;
}

export interface ScreenshotSource {
  id: number;
  position: number;
  width: number;
  height: number;
  name: string;
  url: string;
  captions: Record<string, ScreenshotCaption>;
}

export interface ScreenshotLocale {
  locale: string;
  language: string;
  countries: string[];
  isMain: boolean;
}

export interface ScreenshotRenderItem {
  id: number;
  locale: string;
  device: ScreenshotDeviceId;
  position: number;
  url: string;
  renderedAt: string;
}

export interface ScreenshotPushEvent {
  locale: string;
  device: ScreenshotDeviceId;
  status: "success" | "failed" | string;
  error: string | null;
  createdAt: string;
  uploaded: number;
}

export interface ScreenshotStudioData {
  appId: number;
  mainLocale: string;
  style: ScreenshotStyle;
  devices: Record<ScreenshotDeviceId, ScreenshotDevice>;
  locales: ScreenshotLocale[];
  sources: ScreenshotSource[];
  renders: ScreenshotRenderItem[];
  pushEvents: ScreenshotPushEvent[];
}

export interface ScreenshotPushResult {
  results: { locale: string; device: ScreenshotDeviceId; uploaded: number; error: string | null }[];
  versionState: string;
}
