import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/api-client", () => ({
  getAnalyticsTimeseries: vi.fn(),
}));

import { getAnalyticsTimeseries } from "@/lib/api-client";
import { GET } from "./route";

describe("GET /api/analytics/timeseries", () => {
  it("forwards the interval query param, defaulting to day", async () => {
    vi.mocked(getAnalyticsTimeseries).mockResolvedValue([]);

    await GET(new NextRequest("http://localhost:3000/api/analytics/timeseries"));
    expect(getAnalyticsTimeseries).toHaveBeenCalledWith("day");

    await GET(new NextRequest("http://localhost:3000/api/analytics/timeseries?interval=week"));
    expect(getAnalyticsTimeseries).toHaveBeenCalledWith("week");
  });
});
