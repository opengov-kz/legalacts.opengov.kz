import Link from "next/link";
import type { Dictionary } from "@/lib/i18n/dictionaries";

function hrefForPage(basePath: string, searchParams: Record<string, string>, page: number): string {
  const query = new URLSearchParams(searchParams);
  if (page > 1) query.set("page", String(page));
  else query.delete("page");
  const qs = query.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

export function Pagination({
  page,
  hasNextPage,
  basePath,
  searchParams,
  dict,
}: {
  page: number;
  hasNextPage: boolean;
  basePath: string;
  searchParams: Record<string, string>;
  dict: Dictionary;
}) {
  return (
    <div className="flex items-center justify-between pt-4 text-sm">
      {page > 1 ? (
        <Link href={hrefForPage(basePath, searchParams, page - 1)}>{dict.documents.prevPage}</Link>
      ) : (
        <span className="text-ink-muted">{dict.documents.prevPage}</span>
      )}
      <span>{dict.documents.pageOf(page)}</span>
      {hasNextPage ? (
        <Link href={hrefForPage(basePath, searchParams, page + 1)}>{dict.documents.nextPage}</Link>
      ) : (
        <span className="text-ink-muted">{dict.documents.nextPage}</span>
      )}
    </div>
  );
}
