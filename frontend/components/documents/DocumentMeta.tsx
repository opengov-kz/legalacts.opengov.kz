import { Badge } from "@/components/ui/badge";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { Locale } from "@/lib/i18n/locales";
import type { DocumentDetail } from "@/types/api";

function titleFor(doc: DocumentDetail, locale: Locale, dict: Dictionary): string {
  const title = locale === "kk" ? doc.title_kk ?? doc.title_ru : doc.title_ru ?? doc.title_kk;
  return title ?? dict.documents.untitled;
}

export function DocumentMeta({
  document,
  locale,
  dict,
}: {
  document: DocumentDetail;
  locale: Locale;
  dict: Dictionary;
}) {
  return (
    <div>
      <h1 className="text-2xl font-semibold">{titleFor(document, locale, dict)}</h1>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-secondary">
        <Badge>{document.section}</Badge>
        {document.status && <span>{document.status}</span>}
        {document.doc_type && <span>{`· ${document.doc_type}`}</span>}
        {document.government_body && (
          <>
            <span>·</span>
            <span>{document.government_body}</span>
          </>
        )}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        <dt className="text-ink-muted">{dict.documents.createdDate}</dt>
        <dd>{document.created_date ?? "—"}</dd>
        <dt className="text-ink-muted">{dict.documents.discussionEndDate}</dt>
        <dd>{document.discussion_end_date ?? "—"}</dd>
        <dt className="text-ink-muted">{dict.documents.reactions}</dt>
        <dd>
          {document.likes_count ?? 0} / {document.dislikes_count ?? 0}
        </dd>
        <dt className="text-ink-muted">{dict.documents.comments}</dt>
        <dd>{document.comments_total ?? 0}</dd>
      </dl>
      <a
        href={document.url}
        target="_blank"
        rel="noreferrer"
        className="mt-4 inline-block text-sm font-medium underline"
      >
        {dict.documents.originalLink}
      </a>
    </div>
  );
}
