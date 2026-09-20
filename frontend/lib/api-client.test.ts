import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getAnalyticsSummary,
  getAnalyticsTimeseries,
  getCrawlStatus,
  getDocument,
  getDocuments,
} from "./api-client";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api-client", () => {
  beforeEach(() => {
    vi.stubEnv("FASTAPI_BASE_URL", "http://api.test:8000");
    vi.stubEnv("API_KEY", "test-key");
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("getDocuments builds the query string, sends X-API-Key, and returns parsed JSON", async () => {
    const mockDocs = [{ id: 1, external_id: 10, section: "npa" }];
    vi.mocked(fetch).mockResolvedValue(jsonResponse(mockDocs));

    const result = await getDocuments({ section: "npa", status: "Архив", page: 2 });

    expect(result).toEqual(mockDocs);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe(
      "http://api.test:8000/documents?section=npa&status=%D0%90%D1%80%D1%85%D0%B8%D0%B2&page=2",
    );
    expect((init?.headers as Record<string, string>)["X-API-Key"]).toBe("test-key");
  });

  it("getDocuments omits unset filters from the query string", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([]));

    await getDocuments({});

    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("http://api.test:8000/documents?");
  });

  it("getDocument returns the parsed document on 200", async () => {
    const doc = { id: 1, comments: [] };
    vi.mocked(fetch).mockResolvedValue(jsonResponse(doc));

    const result = await getDocument(1);

    expect(result).toEqual(doc);
    const [url] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("http://api.test:8000/documents/1");
  });

  it("getDocument returns null on 404", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "Document not found" }, 404));

    const result = await getDocument(999);

    expect(result).toBeNull();
  });

  it("getDocument throws on a 500 response", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "boom" }, 500));

    await expect(getDocument(1)).rejects.toThrow(/500/);
  });

  it("getAnalyticsSummary calls /analytics/summary", async () => {
    const summary = { documents_by_section: [], documents_by_status: [], total_documents: 0, total_comments: 0 };
    vi.mocked(fetch).mockResolvedValue(jsonResponse(summary));

    const result = await getAnalyticsSummary();

    expect(result).toEqual(summary);
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe("http://api.test:8000/analytics/summary?");
  });

  it("getAnalyticsTimeseries forwards the interval query param", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([{ bucket: "2026-01-01", count: 3 }]));

    await getAnalyticsTimeseries("week");

    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe(
      "http://api.test:8000/analytics/timeseries?interval=week",
    );
  });

  it("getCrawlStatus calls /crawl/status", async () => {
    const status = { counts: [], last_processed_at: null, recent_errors: [] };
    vi.mocked(fetch).mockResolvedValue(jsonResponse(status));

    const result = await getCrawlStatus();

    expect(result).toEqual(status);
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe("http://api.test:8000/crawl/status?");
  });

  it("throws with the upstream status code when a request fails", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "nope" }, 503));

    await expect(getCrawlStatus()).rejects.toThrow(/503/);
  });

  it("propagates a network failure (fetch rejecting) as a thrown error", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("fetch failed"));

    await expect(getDocuments({})).rejects.toThrow("fetch failed");
  });
});
