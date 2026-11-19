// Thin JSON client for the local dashboard server. Every request stays on the
// same origin (CSP connect-src 'self'); the server alone talks to Apple.

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

async function parse<T>(response: Response): Promise<T> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Non-JSON bodies only happen on unexpected server failures.
  }
  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload
        ? String((payload as { error: unknown }).error)
        : `Local request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

export async function apiGet<T>(path: string, query?: Query, signal?: AbortSignal): Promise<T> {
  return parse<T>(await fetch(withQuery(path, query), { signal, headers: { Accept: "application/json" } }));
}

// The server rejects empty POST bodies, so actions without fields still send {}.
export async function apiPost<T>(path: string, body: object = {}): Promise<T> {
  return parse<T>(
    await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    }),
  );
}
