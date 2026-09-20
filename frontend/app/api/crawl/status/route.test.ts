import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({
  getCrawlStatus: vi.fn(),
}));

import { getCrawlStatus } from "@/lib/api-client";
import { GET } from "./route";

describe("GET /api/crawl/status", () => {
  it("returns the crawl status as JSON", async () => {
    const status = { counts: [], last_processed_at: null, recent_errors: [] };
    vi.mocked(getCrawlStatus).mockResolvedValue(status);

    const response = await GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(status);
  });

  it("returns 500 with a generic error body when getCrawlStatus throws, logging server-side", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(getCrawlStatus).mockRejectedValue(new Error("upstream down"));

    const response = await GET();

    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ error: "Внутренняя ошибка сервера" });
    expect(consoleErrorSpy).toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });
});
