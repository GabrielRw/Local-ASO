// Renders captioned App Store screenshots on a canvas. The web view's system fonts shape
// every script (CJK, Thai, Arabic and Hebrew right-to-left), so nothing is bundled.

export interface ScreenshotStyle {
  background: string;
  backgroundTo: string;
  text: string;
  accent: string;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const RTL_LOCALES = new Set(["ar-SA", "he"]);
const FONT_STACK = '-apple-system, BlinkMacSystemFont, "Helvetica Neue", "Hiragino Sans", "PingFang SC", "Apple SD Gothic Neo", system-ui, sans-serif';

export function isRtl(locale: string): boolean {
  return RTL_LOCALES.has(locale);
}

/** Greedy word wrap; scripts without spaces (CJK, Thai) wrap per character. */
export function wrapText(measure: (text: string) => number, text: string, maxWidth: number): string[] {
  const clean = text.trim().replace(/\s+/g, " ");
  if (!clean) return [];
  const spaced = clean.includes(" ");
  const units = spaced ? clean.split(" ") : Array.from(clean);
  const joiner = spaced ? " " : "";
  const lines: string[] = [];
  let line = "";
  for (const unit of units) {
    const candidate = line ? `${line}${joiner}${unit}` : unit;
    if (line && measure(candidate) > maxWidth) {
      lines.push(line);
      line = unit;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** The largest font size (down to a floor) whose wrapped text fits in `maxLines` lines. */
export function fitFont(
  measureAt: (size: number) => (text: string) => number,
  text: string,
  maxWidth: number,
  startSize: number,
  maxLines: number,
  minSize: number,
): { size: number; lines: string[] } {
  for (let size = startSize; size >= minSize; size = Math.floor(size * 0.92)) {
    const lines = wrapText(measureAt(size), text, maxWidth);
    if (lines.length <= maxLines) return { size, lines };
  }
  const lines = wrapText(measureAt(minSize), text, maxWidth).slice(0, maxLines);
  return { size: minSize, lines };
}

/**
 * Re-wrap into the same number of lines at the narrowest width that still fits, so a
 * two-line caption doesn't leave one word (or one CJK character) alone on a line.
 */
export function balanceLines(measure: (text: string) => number, text: string, maxWidth: number, lines: string[]): string[] {
  if (lines.length < 2) return lines;
  let low = maxWidth / 2;
  let high = maxWidth;
  let best = lines;
  for (let step = 0; step < 12; step++) {
    const middle = (low + high) / 2;
    const attempt = wrapText(measure, text, middle);
    if (attempt.length <= lines.length && attempt.every((line) => measure(line) <= maxWidth)) {
      best = attempt;
      high = middle;
    } else {
      low = middle;
    }
  }
  return best;
}

/**
 * Where the screenshot goes: centred below the caption, keeping its aspect ratio, at
 * most 84% of the canvas width and a little taller than the space left, so it may run
 * off the bottom edge as App Store marketing shots usually do. On a wider canvas (iPad)
 * a phone capture is sized by height instead of being cropped to a sliver.
 */
export function screenshotRect(
  canvasWidth: number,
  canvasHeight: number,
  captionBottom: number,
  imageWidth: number,
  imageHeight: number,
): Rect {
  const byHeight = ((canvasHeight - captionBottom) * 1.1 * imageWidth) / imageHeight;
  const width = Math.round(Math.min(canvasWidth * 0.84, byHeight));
  const height = Math.round((width * imageHeight) / imageWidth);
  return { x: Math.round((canvasWidth - width) / 2), y: Math.round(captionBottom), width, height };
}

export interface RenderInput {
  image: CanvasImageSource & { width: number; height: number };
  width: number;
  height: number;
  headline: string;
  subline: string;
  style: ScreenshotStyle;
  locale: string;
}

export function renderScreenshot(canvas: HTMLCanvasElement, input: RenderInput): void {
  const { width, height, style } = input;
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas is not available in this browser");
  const gradient = context.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, style.background);
  gradient.addColorStop(1, style.backgroundTo);
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);

  const rtl = isRtl(input.locale);
  context.direction = rtl ? "rtl" : "ltr";
  context.textAlign = "center";
  context.textBaseline = "top";
  const margin = width * 0.08;
  const textWidth = width - margin * 2;
  const measureAt = (weight: number) => (size: number) => (text: string) => {
    context.font = `${weight} ${size}px ${FONT_STACK}`;
    return context.measureText(text).width;
  };

  let y = height * 0.06;
  const headline = fitFont(measureAt(700), input.headline, textWidth, Math.round(width * 0.082), 3, Math.round(width * 0.05));
  const headlineLines = balanceLines(measureAt(700)(headline.size), input.headline, textWidth, headline.lines);
  context.fillStyle = style.text;
  context.font = `700 ${headline.size}px ${FONT_STACK}`;
  for (const line of headlineLines) {
    context.fillText(line, width / 2, y);
    y += headline.size * 1.15;
  }
  if (input.subline.trim()) {
    y += headline.size * 0.25;
    const subline = fitFont(measureAt(500), input.subline, textWidth, Math.round(width * 0.042), 2, Math.round(width * 0.03));
    const sublineLines = balanceLines(measureAt(500)(subline.size), input.subline, textWidth, subline.lines);
    context.fillStyle = style.accent;
    context.font = `500 ${subline.size}px ${FONT_STACK}`;
    for (const line of sublineLines) {
      context.fillText(line, width / 2, y);
      y += subline.size * 1.25;
    }
  }

  const rect = screenshotRect(width, height, y + height * 0.035, input.image.width, input.image.height);
  const radius = rect.width * 0.06;
  context.save();
  context.shadowColor = "rgba(0, 0, 0, 0.35)";
  context.shadowBlur = width * 0.03;
  context.shadowOffsetY = width * 0.01;
  context.beginPath();
  context.roundRect(rect.x, rect.y, rect.width, rect.height, radius);
  context.fillStyle = "#000";
  context.fill();
  context.restore();
  context.save();
  context.beginPath();
  context.roundRect(rect.x, rect.y, rect.width, rect.height, radius);
  context.clip();
  context.drawImage(input.image, rect.x, rect.y, rect.width, rect.height);
  context.restore();
}

export function canvasToPng(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Could not encode the screenshot"))), "image/png"),
  );
}

export function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not load the screenshot"));
    image.src = url;
  });
}
