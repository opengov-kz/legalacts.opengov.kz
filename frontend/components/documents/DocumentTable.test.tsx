import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { DocumentTable } from "./DocumentTable";
import type { DocumentListItem } from "@/types/api";

const doc: DocumentListItem = {
  id: 1,
  external_id: 100,
  section: "npa",
  url: "https://legalacts.egov.kz/npa/view?id=100",
  title_ru: "Заголовок RU",
  title_kk: "Атауы KK",
  status: "Архив",
  doc_type: "Приказ",
  government_body: "Министерство",
  created_date: "2026-01-01",
  discussion_end_date: "2026-02-01",
  comments_total: 5,
  likes_count: 2,
  dislikes_count: 1,
  first_seen_at: "2026-01-01T00:00:00Z",
  last_checked_at: "2026-01-02T00:00:00Z",
};

describe("DocumentTable", () => {
  it("renders one row per document, linking to the detail page, titled per locale", () => {
    render(<DocumentTable documents={[doc]} locale="ru" dict={getDictionary("ru")} />);

    const link = screen.getByRole("link", { name: "Заголовок RU" });
    expect(link).toHaveAttribute("href", "/ru/documents/1");
    expect(screen.getByText("Архив")).toBeInTheDocument();
  });

  it("falls back to title_ru when title_kk is null and locale is kk", () => {
    render(
      <DocumentTable
        documents={[{ ...doc, title_kk: null }]}
        locale="kk"
        dict={getDictionary("kk")}
      />,
    );

    expect(screen.getByRole("link", { name: "Заголовок RU" })).toBeInTheDocument();
  });

  it("shows the empty state when there are no documents", () => {
    render(<DocumentTable documents={[]} locale="ru" dict={getDictionary("ru")} />);
    expect(screen.getByText("Документы не найдены")).toBeInTheDocument();
  });

  it("falls back to a placeholder title when both title_ru and title_kk are null", () => {
    render(
      <DocumentTable
        documents={[{ ...doc, title_ru: null, title_kk: null }]}
        locale="ru"
        dict={getDictionary("ru")}
      />,
    );

    expect(screen.getByRole("link", { name: "Без названия" })).toBeInTheDocument();
  });
});
