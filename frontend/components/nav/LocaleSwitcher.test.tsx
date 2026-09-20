import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { LocaleSwitcher } from "./LocaleSwitcher";

describe("LocaleSwitcher", () => {
  it("renders a link to the kk version of the current path when active locale is ru", () => {
    render(
      <LocaleSwitcher activeLocale="ru" currentPath="/ru/documents?section=npa" dict={getDictionary("ru")} />,
    );

    const kkLink = screen.getByRole("link", { name: "KK" });
    expect(kkLink).toHaveAttribute("href", "/kk/documents?section=npa");

    const ruLink = screen.getByRole("link", { name: "RU" });
    expect(ruLink).toHaveAttribute("aria-current", "page");
  });

  it("renders a link to the ru version of the current path when active locale is kk", () => {
    render(<LocaleSwitcher activeLocale="kk" currentPath="/kk/analytics" dict={getDictionary("ru")} />);

    expect(screen.getByRole("link", { name: "RU" })).toHaveAttribute("href", "/ru/analytics");
    expect(screen.getByRole("link", { name: "KK" })).toHaveAttribute("aria-current", "page");
  });
});
