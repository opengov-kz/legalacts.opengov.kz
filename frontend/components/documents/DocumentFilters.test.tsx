import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { DocumentFilters } from "./DocumentFilters";

describe("DocumentFilters", () => {
  it("renders links for every known section, marking the active one, and preserves it when unfiltered", () => {
    render(<DocumentFilters locale="ru" section={undefined} dict={getDictionary("ru")} />);

    const npaLink = screen.getByRole("link", { name: "npa" });
    expect(npaLink).toHaveAttribute("href", "/ru/documents?section=npa");

    const allLink = screen.getByRole("link", { name: "Все разделы" });
    expect(allLink).toHaveAttribute("aria-current", "page");
  });

  it("marks the currently selected section as active", () => {
    render(<DocumentFilters locale="ru" section="arv" dict={getDictionary("ru")} />);

    expect(screen.getByRole("link", { name: "arv" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "kdrp" })).toHaveAttribute("href", "/ru/documents?section=kdrp");
  });
});
