import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { Locale } from "@/lib/i18n/locales";
import type { DocumentListItem } from "@/types/api";

function titleFor(doc: DocumentListItem, locale: Locale): string {
  if (locale === "kk") return doc.title_kk ?? doc.title_ru ?? "";
  return doc.title_ru ?? doc.title_kk ?? "";
}

export function DocumentTable({
  documents,
  locale,
  dict,
}: {
  documents: DocumentListItem[];
  locale: Locale;
  dict: Dictionary;
}) {
  if (documents.length === 0) {
    return <p className="py-8 text-center text-ink-secondary">{dict.documents.empty}</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{dict.documents.title}</TableHead>
          <TableHead>{dict.documents.filterSection}</TableHead>
          <TableHead>{dict.documents.filterStatus}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.map((doc) => (
          <TableRow key={doc.id}>
            <TableCell>
              <Link href={`/${locale}/documents/${doc.id}`} className="font-medium hover:underline">
                {titleFor(doc, locale)}
              </Link>
            </TableCell>
            <TableCell>
              <Badge>{doc.section}</Badge>
            </TableCell>
            <TableCell>{doc.status ?? "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
