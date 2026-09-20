export function getServerEnv() {
  const fastApiBaseUrl = process.env.FASTAPI_BASE_URL;
  if (!fastApiBaseUrl) {
    throw new Error("FASTAPI_BASE_URL environment variable is required but was not set");
  }

  const apiKey = process.env.API_KEY;
  if (!apiKey) {
    throw new Error("API_KEY environment variable is required but was not set");
  }

  return { fastApiBaseUrl, apiKey };
}
