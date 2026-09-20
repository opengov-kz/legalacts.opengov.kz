import { describe, expect, it } from "vitest";
import { DEFAULT_LOCALE, isLocale, LOCALES } from "./locales";

describe("locales", () => {
  it("lists ru and kk", () => {
    expect(LOCALES).toEqual(["ru", "kk"]);
  });

  it("defaults to ru", () => {
    expect(DEFAULT_LOCALE).toBe("ru");
  });

  it("isLocale accepts only known locales", () => {
    expect(isLocale("ru")).toBe(true);
    expect(isLocale("kk")).toBe(true);
    expect(isLocale("en")).toBe(false);
    expect(isLocale("")).toBe(false);
  });
});
