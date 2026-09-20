"use client";

import { Bar, BarChart, CartesianGrid, Cell, LabelList, Tooltip, XAxis, YAxis } from "recharts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const CATEGORICAL_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
const OTHER_COLOR_LIGHT = "#c3c2b7";
const MAX_SLOTS = 8;

interface CategoryDatum {
  label: string;
  count: number;
}

function reduceToSlots(data: CategoryDatum[], otherLabel: string): CategoryDatum[] {
  const sorted = [...data].sort((a, b) => b.count - a.count);
  if (sorted.length <= MAX_SLOTS) return sorted;

  const kept = sorted.slice(0, MAX_SLOTS);
  const folded = sorted.slice(MAX_SLOTS).reduce((sum, d) => sum + d.count, 0);
  return [...kept, { label: otherLabel, count: folded }];
}

export function CategoryBarChart({
  data,
  otherLabel,
  tableCaption,
}: {
  data: CategoryDatum[];
  otherLabel: string;
  tableCaption: string;
}) {
  const slots = reduceToSlots(data, otherLabel);

  return (
    <div>
      <BarChart width={480} height={260} data={slots} margin={{ top: 16, right: 8, left: 0, bottom: 8 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis dataKey="label" stroke="var(--ink-muted)" fontSize={12} />
        <YAxis stroke="var(--ink-muted)" fontSize={12} allowDecimals={false} />
        <Tooltip contentStyle={{ background: "var(--surface-card)", border: "1px solid var(--gridline)" }} />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          <LabelList dataKey="count" position="top" fill="var(--ink-primary)" fontSize={12} />
          {slots.map((slot, index) => (
            <Cell
              key={slot.label}
              fill={
                slot.label === otherLabel
                  ? OTHER_COLOR_LIGHT
                  : CATEGORICAL_LIGHT[index % CATEGORICAL_LIGHT.length]
              }
            />
          ))}
        </Bar>
      </BarChart>

      <Table aria-label={tableCaption} className="mt-2">
        <TableHeader>
          <TableRow>
            <TableHead>{tableCaption}</TableHead>
            <TableHead>Count</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {slots.map((slot) => (
            <TableRow key={slot.label}>
              <TableCell>{slot.label}</TableCell>
              <TableCell>{slot.count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
