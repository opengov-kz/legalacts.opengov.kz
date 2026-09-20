import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { CrawlErrorsTable } from "./CrawlErrorsTable";

describe("CrawlErrorsTable", () => {
  it("renders a row per error with url, page_type, message, and timestamp", () => {
    render(
      <CrawlErrorsTable
        errors={[
          {
            url: "https://legalacts.egov.kz/npa/view?id=1",
            page_type: "document",
            last_error: "timeout",
            processed_at: "2026-09-19T10:00:00+00:00",
          },
        ]}
        dict={getDictionary("ru")}
      />,
    );

    expect(screen.getByText("timeout")).toBeInTheDocument();
    expect(screen.getByText("https://legalacts.egov.kz/npa/view?id=1")).toBeInTheDocument();
  });

  it("shows the no-errors state when the list is empty", () => {
    render(<CrawlErrorsTable errors={[]} dict={getDictionary("ru")} />);
    expect(screen.getByText("Ошибок нет")).toBeInTheDocument();
  });
});
