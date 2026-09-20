import { getServerEnv } from "./env";
import type {
  AnalyticsSummary,
  CrawlStatus,
  DocumentDetail,
  DocumentListItem,
  TimeseriesPoint,
} from "@/types/api";

async function apiFetch(
  path: string,
  searchParams?: Record<string, string | number | undefined>,
): Promise<Response> {
  const { fastApiBaseUrl, apiKey } = getServerEnv();

  let url = `${fastApiBaseUrl}${path}`;

  if (searchParams) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(searchParams)) {
      if (value !== undefined) query.set(key, String(value));
    }
    url += `?${query.toString()}`;
  }

  return fetch(url, {
    headers: { "X-API-Key": apiKey },
    cache: "no-store",
  });
}

async function fetchJson<T>(
  path: string,
  searchParams: Record<string, string | number | undefined> = {},
): Promise<T> {
  const response = await apiFetch(path, searchParams || {});

  if (!response.ok) {
    throw new Error(`FastAPI request to ${path} failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function getDocuments(params: {
  section?: string;
  status?: string;
  page?: number;
}): Promise<DocumentListItem[]> {
  return fetchJson<DocumentListItem[]>("/documents", {
    section: params.section,
    status: params.status,
    page: params.page,
  });
}

export async function getDocument(id: number): Promise<DocumentDetail | null> {
  const response = await apiFetch(`/documents/${id}`);

  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`FastAPI request to /documents/${id} failed with status ${response.status}`);
  }

  return response.json() as Promise<DocumentDetail>;
}

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  return fetchJson<AnalyticsSummary>("/analytics/summary");
}

export async function getAnalyticsTimeseries(interval: "day" | "week"): Promise<TimeseriesPoint[]> {
  return fetchJson<TimeseriesPoint[]>("/analytics/timeseries", { interval });
}

export async function getCrawlStatus(): Promise<CrawlStatus> {
  return fetchJson<CrawlStatus>("/crawl/status");
}
