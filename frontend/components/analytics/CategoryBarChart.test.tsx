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
    render(<CategoryBarChart data={many} otherLabel="Прочее" tableCaption="Test" />);

    expect(screen.getAllByRole("row")).toHaveLength(1 + 8 + 1); // header + 8 slots + "Прочее"
    expect(screen.getByRole("cell", { name: "Прочее" })).toBeInTheDocument();
    // s8 (count 2) + s9 (count 1) folded => 3
    const otherRow = screen.getByRole("cell", { name: "Прочее" }).closest("tr")!;
    expect(otherRow).toHaveTextContent("3");
  });
});
