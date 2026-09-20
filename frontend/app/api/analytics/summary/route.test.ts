import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({
  getAnalyticsSummary: vi.fn(),
}));

import { getAnalyticsSummary } from "@/lib/api-client";
import { GET } from "./route";

describe("GET /api/analytics/summary", () => {
  it("returns the summary as JSON", async () => {
    const summary = { documents_by_section: [], documents_by_status: [], total_documents: 0, total_comments: 0 };
    vi.mocked(getAnalyticsSummary).mockResolvedValue(summary);

    const response = await GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(summary);
  });

  it("returns 500 with a generic error body when getAnalyticsSummary throws, logging server-side", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(getAnalyticsSummary).mockRejectedValue(new Error("upstream down"));

    const response = await GET();

    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ error: "Внутренняя ошибка сервера" });
    expect(consoleErrorSpy).toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });
});
