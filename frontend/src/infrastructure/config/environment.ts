export const environment = {
  appName: import.meta.env.VITE_APP_NAME ?? "Creator_OS",
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
} as const;
