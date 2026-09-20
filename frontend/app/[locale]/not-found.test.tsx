import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const usePathnameMock = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}));

import NotFound from "./not-found";

describe("[locale] not-found", () => {
  it("renders in Russian when the URL's locale segment is ru", () => {
    usePathnameMock.mockReturnValue("/ru/documents/999");
    render(<NotFound />);
    expect(screen.getByText("Страница не найдена")).toBeInTheDocument();
  });

  it("renders in Kazakh when the URL's locale segment is kk", () => {
    usePathnameMock.mockReturnValue("/kk/documents/999");
    render(<NotFound />);
    expect(screen.getByText("Бет табылмады")).toBeInTheDocument();
  });

  it("falls back to the default locale when the pathname has no recognizable locale segment", () => {
    usePathnameMock.mockReturnValue(null);
    render(<NotFound />);
    expect(screen.getByText("Страница не найдена")).toBeInTheDocument();
  });
});
