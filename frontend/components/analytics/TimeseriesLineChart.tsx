"use client";

import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { TimeseriesPoint } from "@/types/api";

const SERIES_COLOR_LIGHT = "#2a78d6";

export function TimeseriesLineChart({
  points,
  tableCaption,
}: {
  points: TimeseriesPoint[];
  tableCaption: string;
}) {
  return (
    <div>
      <LineChart width={480} height={260} data={points} margin={{ top: 16, right: 8, left: 0, bottom: 8 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis dataKey="bucket" stroke="var(--ink-muted)" fontSize={12} tickFormatter={(v) => String(v).slice(0, 10)} />
        <YAxis stroke="var(--ink-muted)" fontSize={12} allowDecimals={false} />
        <Tooltip contentStyle={{ background: "var(--surface-card)", border: "1px solid var(--gridline)" }} />
        <Line type="monotone" dataKey="count" stroke={SERIES_COLOR_LIGHT} strokeWidth={2} dot={{ r: 4 }} />
      </LineChart>

      <Table aria-label={tableCaption} className="mt-2">
        <TableHeader>
          <TableRow>
            <TableHead>Bucket</TableHead>
            <TableHead>Count</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {points.map((point) => (
            <TableRow key={point.bucket}>
              <TableCell>{point.bucket.slice(0, 10)}</TableCell>
              <TableCell>{point.count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
