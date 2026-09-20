import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ru/documents",
  useSearchParams: () => new URLSearchParams("section=npa"),
}));

import { SiteHeader } from "./SiteHeader";

describe("SiteHeader", () => {
  it("renders nav links for the active locale and passes the current path to the locale switcher", () => {
    render(<SiteHeader locale="ru" />);

    expect(screen.getByRole("link", { name: "Документы" })).toHaveAttribute("href", "/ru/documents");
    expect(screen.getByRole("link", { name: "Аналитика" })).toHaveAttribute("href", "/ru/analytics");
    expect(screen.getByRole("link", { name: "Статус обхода" })).toHaveAttribute("href", "/ru/crawl-status");

    const kkLink = screen.getByRole("link", { name: "KK" });
    expect(kkLink).toHaveAttribute("href", "/kk/documents?section=npa");
  });

  it("renders Kazakh nav labels for the kk locale", () => {
    render(<SiteHeader locale="kk" />);

    expect(screen.getByRole("link", { name: "Құжаттар" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Аналитика" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Аралау мәртебесі" })).toBeInTheDocument();
  });
});
