import type { ScreenshotDeviceId, ScreenshotRenderItem, ScreenshotStudioData } from "./types";

export const CAPTION_LIMITS = { headline: 40, subline: 80 } as const;

export interface RenderJob {
  locale: string;
  device: ScreenshotDeviceId;
  sourceId: number;
  position: number;
}

/** Every locale x device x screenshot that has a headline in that locale. */
export function renderJobs(data: ScreenshotStudioData, devices: ScreenshotDeviceId[]): RenderJob[] {
  const jobs: RenderJob[] = [];
  for (const { locale } of data.locales) {
    for (const device of devices) {
      for (const source of data.sources) {
        if (source.captions[locale]?.headline?.trim()) {
          jobs.push({ locale, device, sourceId: source.id, position: source.position });
        }
      }
    }
  }
  return jobs;
}

/** Render counts per locale and device, only for positions that still exist. */
export function renderCounts(
  renders: ScreenshotRenderItem[],
  sourceCount: number,
): Map<string, Partial<Record<ScreenshotDeviceId, number>>> {
  const counts = new Map<string, Partial<Record<ScreenshotDeviceId, number>>>();
  for (const render of renders) {
    if (render.position > sourceCount) continue;
    const entry = counts.get(render.locale) ?? {};
    entry[render.device] = (entry[render.device] ?? 0) + 1;
    counts.set(render.locale, entry);
  }
  return counts;
}

/** Locales with no caption at all for at least one screenshot. */
export function missingCaptions(data: ScreenshotStudioData, locale: string): number {
  return data.sources.filter((source) => !source.captions[locale]?.headline?.trim()).length;
}
