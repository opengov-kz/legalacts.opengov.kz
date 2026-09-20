import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { CrawlStatusCount } from "@/types/api";

export function CrawlStatusTable({
  counts,
  lastProcessedAt,
  dict,
}: {
  counts: CrawlStatusCount[];
  lastProcessedAt: string | null;
  dict: Dictionary;
}) {
  return (
    <div>
      <p className="mb-3 text-sm text-ink-secondary">
        {dict.crawlStatus.lastProcessedAt}:{" "}
        <span>{lastProcessedAt ?? dict.crawlStatus.never}</span>
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{dict.crawlStatus.pageType}</TableHead>
            <TableHead>{dict.crawlStatus.status}</TableHead>
            <TableHead>{dict.crawlStatus.count}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {counts.map((row) => (
            <TableRow key={`${row.page_type}-${row.status}`}>
              <TableCell>{row.page_type}</TableCell>
              <TableCell>{row.status}</TableCell>
              <TableCell>{row.count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
