import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { Pagination } from "./Pagination";

describe("Pagination", () => {
  it("links next/prev preserving other query params, disables prev on page 1", () => {
    render(
      <Pagination
        locale="ru"
        page={1}
        hasNextPage
        basePath="/ru/documents"
        searchParams={{ section: "npa" }}
        dict={getDictionary("ru")}
      />,
    );

    expect(screen.getByText("Назад")).not.toHaveAttribute("href");
    expect(screen.getByRole("link", { name: "Вперёд" })).toHaveAttribute(
      "href",
      "/ru/documents?section=npa&page=2",
    );
  });

  it("disables next when hasNextPage is false", () => {
    render(
      <Pagination
        locale="ru"
        page={3}
        hasNextPage={false}
        basePath="/ru/documents"
        searchParams={{}}
        dict={getDictionary("ru")}
      />,
    );

    expect(screen.getByText("Вперёд")).not.toHaveAttribute("href");
    expect(screen.getByRole("link", { name: "Назад" })).toHaveAttribute("href", "/ru/documents?page=2");
  });
});
