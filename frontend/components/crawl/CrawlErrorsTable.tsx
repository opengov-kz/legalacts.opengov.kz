import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { CrawlError } from "@/types/api";

export function CrawlErrorsTable({ errors, dict }: { errors: CrawlError[]; dict: Dictionary }) {
  if (errors.length === 0) {
    return <p className="text-ink-secondary">{dict.crawlStatus.noErrors}</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{dict.crawlStatus.url}</TableHead>
          <TableHead>{dict.crawlStatus.pageType}</TableHead>
          <TableHead>{dict.crawlStatus.error}</TableHead>
          <TableHead>{dict.crawlStatus.processedAt}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {errors.map((err) => (
          <TableRow key={err.url}>
            <TableCell className="max-w-xs truncate">{err.url}</TableCell>
            <TableCell>{err.page_type}</TableCell>
            <TableCell>{err.last_error ?? "—"}</TableCell>
            <TableCell>{err.processed_at ?? "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
