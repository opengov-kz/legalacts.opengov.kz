import { getServerEnv } from "./env";
import type {
  AnalyticsSummary,
  CrawlStatus,
  DocumentDetail,
  DocumentListItem,
  TimeseriesPoint,
} from "@/types/api";

async function fetchJson<T>(
  path: string,
  searchParams: Record<string, string | number | undefined> = {},
): Promise<T> {
  const { fastApiBaseUrl, apiKey } = getServerEnv();

  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (value !== undefined) query.set(key, String(value));
  }

  const url = `${fastApiBaseUrl}${path}?${query.toString()}`;
  const response = await fetch(url, {
    headers: { "X-API-Key": apiKey },
    cache: "no-store",
  });

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
  const { fastApiBaseUrl, apiKey } = getServerEnv();
  const response = await fetch(`${fastApiBaseUrl}/documents/${id}`, {
    headers: { "X-API-Key": apiKey },
    cache: "no-store",
  });

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
