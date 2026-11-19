import type { LocalizationStudio } from "./types";

export { connectionReady } from "@/components/app-store-connect-settings";

/** Countries that can be generated from the main listing (not the main one, not its locale). */
export function selectableTargets(studio: Pick<LocalizationStudio, "countries" | "sourceLocale">): Set<string> {
  return new Set(
    studio.countries.filter((item) => !item.isMain && item.locale !== studio.sourceLocale).map((item) => item.code),
  );
}

