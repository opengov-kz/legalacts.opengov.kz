import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CategoryBarChart } from "./CategoryBarChart";

describe("CategoryBarChart", () => {
  it("renders a table row with the label and count for every category", () => {
    render(
      <CategoryBarChart
        data={[
          { label: "npa", count: 42 },
          { label: "arv", count: 7 },
        ]}
        otherLabel="Прочее"
        tableCaption="Документы по разделам"
        countLabel="Количество"
      />,
    );

    const table = screen.getByRole("table", { name: "Документы по разделам" });
    expect(table).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "npa" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "42" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "arv" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "7" })).toBeInTheDocument();
  });

  it("folds categories past the 8th slot into the provided 'other' label, sorted by count desc", () => {
    const many = Array.from({ length: 10 }, (_, i) => ({ label: `s${i}`, count: 10 - i }));
    render(<CategoryBarChart data={many} otherLabel="Прочее" tableCaption="Test" countLabel="Количество" />);

    expect(screen.getAllByRole("row")).toHaveLength(1 + 8 + 1); // header + 8 slots + "Прочее"
    expect(screen.getByRole("cell", { name: "Прочее" })).toBeInTheDocument();
    // s8 (count 2) + s9 (count 1) folded => 3
    const otherRow = screen.getByRole("cell", { name: "Прочее" }).closest("tr")!;
    expect(otherRow).toHaveTextContent("3");
  });

  it("keeps the top 8 by count (not the first 8 by array order) when the input is not pre-sorted", () => {
    // Deliberately shuffled: counts are not in array order, so a buggy
    // "slice first, sort remainder" implementation would keep the wrong items.
    const counts = [3, 10, 1, 7, 5, 9, 2, 8, 4, 6];
    const shuffled = counts.map((count, i) => ({ label: `x${i}`, count }));
    // Two smallest counts are 1 (x2) and 2 (x6) => folded count should be 3.
    // Labels for counts 1 and 2 must NOT appear as their own rows.

    render(<CategoryBarChart data={shuffled} otherLabel="Прочее" tableCaption="Test" countLabel="Количество" />);

    expect(screen.getAllByRole("row")).toHaveLength(1 + 8 + 1); // header + 8 slots + "Прочее"
    expect(screen.queryByRole("cell", { name: "x2" })).not.toBeInTheDocument(); // count 1, folded
    expect(screen.queryByRole("cell", { name: "x6" })).not.toBeInTheDocument(); // count 2, folded
    // Top 8 by count are counts 3,4,5,6,7,8,9,10 => labels x0,x8,x4,x9,x3,x7,x1,x5
    for (const label of ["x0", "x8", "x4", "x9", "x3", "x7", "x1", "x5"]) {
      expect(screen.getByRole("cell", { name: label })).toBeInTheDocument();
    }
    const otherRow = screen.getByRole("cell", { name: "Прочее" }).closest("tr")!;
    expect(otherRow).toHaveTextContent("3"); // 1 + 2 folded
  });
});
