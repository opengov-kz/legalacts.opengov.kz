import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { DocumentMeta } from "./DocumentMeta";
import type { DocumentDetail } from "@/types/api";

const doc: DocumentDetail = {
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
  comments: [],
};

describe("DocumentMeta", () => {
  it("renders the localized title, key metadata fields, and a link to the original", () => {
    render(<DocumentMeta document={doc} locale="ru" dict={getDictionary("ru")} />);

    expect(screen.getByRole("heading", { name: "Заголовок RU" })).toBeInTheDocument();
    expect(screen.getByText("Архив")).toBeInTheDocument();
    expect(screen.getByText("Министерство")).toBeInTheDocument();

    const originalLink = screen.getByRole("link", { name: "Оригинал на legalacts.egov.kz" });
    expect(originalLink).toHaveAttribute("href", doc.url);
  });
});
