import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ redirect: vi.fn() }));

import { redirect } from "next/navigation";
import Page from "./page";

describe("root page", () => {
  it("redirects to the default locale's documents catalog", () => {
    Page();
    expect(redirect).toHaveBeenCalledWith("/ru/documents");
  });
});
