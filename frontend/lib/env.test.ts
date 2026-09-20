import { afterEach, describe, expect, it, vi } from "vitest";
import { getServerEnv } from "./env";

describe("getServerEnv", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns fastApiBaseUrl and apiKey when both are set", () => {
    vi.stubEnv("FASTAPI_BASE_URL", "http://api:8000");
    vi.stubEnv("API_KEY", "secret123");

    expect(getServerEnv()).toEqual({
      fastApiBaseUrl: "http://api:8000",
      apiKey: "secret123",
    });
  });

  it("throws naming FASTAPI_BASE_URL when it is missing", () => {
    vi.stubEnv("FASTAPI_BASE_URL", "");
    vi.stubEnv("API_KEY", "secret123");

    expect(() => getServerEnv()).toThrow(/FASTAPI_BASE_URL/);
  });

  it("throws naming API_KEY when it is missing", () => {
    vi.stubEnv("FASTAPI_BASE_URL", "http://api:8000");
    vi.stubEnv("API_KEY", "");

    expect(() => getServerEnv()).toThrow(/API_KEY/);
  });
});
