import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/api-client", () => ({
  getDocument: vi.fn(),
}));

import { getDocument } from "@/lib/api-client";
import { GET } from "./route";

describe("GET /api/documents/[id]", () => {
  it("returns the document as JSON when found", async () => {
    vi.mocked(getDocument).mockResolvedValue({ id: 42 } as never);

    const response = await GET(new NextRequest("http://localhost:3000/api/documents/42"), {
      params: { id: "42" },
    });

    expect(getDocument).toHaveBeenCalledWith(42);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ id: 42 });
  });

  it("returns 404 when getDocument resolves null", async () => {
    vi.mocked(getDocument).mockResolvedValue(null);

    const response = await GET(new NextRequest("http://localhost:3000/api/documents/999"), {
      params: { id: "999" },
    });

    expect(response.status).toBe(404);
  });

  it("returns 500 when getDocument throws", async () => {
    vi.mocked(getDocument).mockRejectedValue(new Error("upstream down"));

    const response = await GET(new NextRequest("http://localhost:3000/api/documents/1"), {
      params: { id: "1" },
    });

    expect(response.status).toBe(500);
  });
});
