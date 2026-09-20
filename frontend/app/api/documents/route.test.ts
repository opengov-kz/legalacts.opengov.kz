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

  it("defaults page to 1 when the page param is absent", async () => {
    vi.mocked(getDocuments).mockResolvedValue([{ id: 1 } as never]);

    const request = new NextRequest("http://localhost:3000/api/documents");
    await GET(request);

    expect(getDocuments).toHaveBeenCalledWith({
      section: undefined,
      status: undefined,
      page: 1,
    });
  });

  it("clamps invalid page values (NaN, 0, negative) to 1", async () => {
    vi.mocked(getDocuments).mockResolvedValue([{ id: 1 } as never]);

    for (const rawPage of ["abc", "0", "-5"]) {
      vi.mocked(getDocuments).mockClear();
      const request = new NextRequest(`http://localhost:3000/api/documents?page=${rawPage}`);
      await GET(request);
      expect(getDocuments).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1 }),
      );
    }
  });
});
