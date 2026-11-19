/** Accepts an App Store ID or an apps.apple.com link containing /id123456789. */
export function parseAppleId(value: string): number | null {
  const text = value.trim();
  if (/^\d{5,12}$/.test(text)) return Number(text);
  try {
    const url = new URL(text);
    if (!["https:", "http:"].includes(url.protocol)) return null;
    if (!/(^|\.)apps\.apple\.com$/.test(url.hostname)) return null;
    const match = url.pathname.match(/\/id(\d{5,12})(?:\/|$)/);
    return match ? Number(match[1]) : null;
  } catch {
    return null;
  }
}
