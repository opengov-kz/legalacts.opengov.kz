import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/api-client", () => ({
  getDocuments: vi.fn(),
}));

import { getDocuments } from "@/lib/api-client";
import { GET } from "./route";

describe("GET /api/documents", () => {
  it("forwards section/status/page query params and returns the result as JSON", async () => {
    vi.mocked(getDocuments).mockResolvedValue([{ id: 1 } as never]);

    const request = new NextRequest("http://localhost:3000/api/documents?section=npa&status=Архив&page=2");
    const response = await GET(request);

    expect(getDocuments).toHaveBeenCalledWith({ section: "npa", status: "Архив", page: 2 });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual([{ id: 1 }]);
  });

  it("returns 500 with an error body when getDocuments throws", async () => {
    vi.mocked(getDocuments).mockRejectedValue(new Error("upstream down"));

    const request = new NextRequest("http://localhost:3000/api/documents");
    const response = await GET(request);

    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ error: "upstream down" });
  });
});
