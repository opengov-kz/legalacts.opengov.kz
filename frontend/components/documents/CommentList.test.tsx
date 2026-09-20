import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { CommentList } from "./CommentList";
import type { Comment } from "@/types/api";

const comment: Comment = {
  id: 1,
  external_comment_id: 10,
  parent_external_comment_id: null,
  author_name: "Иванов И.И.",
  body: "Замечание по пункту 3",
  article_ref: "п. 3",
  status: "accepted",
  commented_at_raw: "10/09 - 11:05",
  first_seen_at: "2026-01-01T00:00:00Z",
};

describe("CommentList", () => {
  it("renders author, body, and article reference for each comment", () => {
    render(<CommentList comments={[comment]} dict={getDictionary("ru")} />);

    expect(screen.getByText("Иванов И.И.")).toBeInTheDocument();
    expect(screen.getByText("Замечание по пункту 3")).toBeInTheDocument();
    expect(screen.getByText("п. 3")).toBeInTheDocument();
  });

  it("shows the empty state when there are no comments", () => {
    render(<CommentList comments={[]} dict={getDictionary("ru")} />);
    expect(screen.getByText("Комментариев нет")).toBeInTheDocument();
  });
});
