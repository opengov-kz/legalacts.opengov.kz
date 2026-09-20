import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { CrawlStatusTable } from "./CrawlStatusTable";

describe("CrawlStatusTable", () => {
  it("renders a row per page_type/status pair and the last-processed timestamp", () => {
    render(
      <CrawlStatusTable
        counts={[
          { page_type: "document", status: "done", count: 120 },
          { page_type: "list", status: "pending", count: 3 },
        ]}
        lastProcessedAt="2026-09-19T10:00:00+00:00"
        dict={getDictionary("ru")}
      />,
    );

    expect(screen.getByText("document")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("2026-09-19T10:00:00+00:00")).toBeInTheDocument();
  });

  it("shows the 'never' label when lastProcessedAt is null", () => {
    render(<CrawlStatusTable counts={[]} lastProcessedAt={null} dict={getDictionary("ru")} />);
    expect(screen.getByText("ещё не было")).toBeInTheDocument();
  });
});
