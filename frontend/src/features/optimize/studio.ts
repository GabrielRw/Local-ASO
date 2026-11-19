import type { AppStoreConnectStatus, LocalizationStudio } from "./types";

/** Push needs saved credentials and a key file readable only by the current user. */
export function connectionReady(connection: AppStoreConnectStatus | undefined): boolean {
  return Boolean(connection?.ready || (connection?.configured && connection?.keyExists && connection?.keyModeSafe));
}

/** Countries that can be generated from the main listing (not the main one, not its locale). */
export function selectableTargets(studio: Pick<LocalizationStudio, "countries" | "sourceLocale">): Set<string> {
  return new Set(
    studio.countries.filter((item) => !item.isMain && item.locale !== studio.sourceLocale).map((item) => item.code),
  );
}

