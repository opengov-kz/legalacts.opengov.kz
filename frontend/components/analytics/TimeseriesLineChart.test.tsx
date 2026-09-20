import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TimeseriesLineChart } from "./TimeseriesLineChart";

describe("TimeseriesLineChart", () => {
  it("renders a table row for every point", () => {
    render(
      <TimeseriesLineChart
        points={[
          { bucket: "2026-01-01T00:00:00+00:00", count: 3 },
          { bucket: "2026-01-02T00:00:00+00:00", count: 5 },
        ]}
        tableCaption="Динамика"
        bucketLabel="Дата"
        countLabel="Количество"
      />,
    );

    const table = screen.getByRole("table", { name: "Динамика" });
    expect(table).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2 points
    expect(screen.getByRole("cell", { name: "3" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "5" })).toBeInTheDocument();
  });
});
