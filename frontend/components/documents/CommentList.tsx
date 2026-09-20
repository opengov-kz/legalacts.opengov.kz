import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { Comment } from "@/types/api";

export function CommentList({ comments, dict }: { comments: Comment[]; dict: Dictionary }) {
  if (comments.length === 0) {
    return <p className="text-ink-secondary">{dict.documents.noComments}</p>;
  }

  return (
    <ul className="flex flex-col gap-4">
      {comments.map((comment) => (
        <li key={comment.id} className="rounded-md border border-gridline p-3">
          <div className="flex items-center justify-between text-sm text-ink-secondary">
            <span>{comment.author_name ?? "—"}</span>
            <span>{comment.commented_at_raw ?? ""}</span>
          </div>
          <p className="mt-1">{comment.body}</p>
          {comment.article_ref && (
            <p className="mt-1 text-xs text-ink-muted">{comment.article_ref}</p>
          )}
        </li>
      ))}
    </ul>
  );
}
