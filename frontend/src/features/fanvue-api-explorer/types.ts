export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type FanvueExplorerResponse = {
  endpoint: string;
  requestParams: Record<string, JsonValue>;
  httpStatus: number;
  elapsedMs: number;
  recordCount: number | null;
  cursor: JsonValue;
  nextPage: JsonValue;
  pagination: Record<string, JsonValue>;
  apiVersion: string;
  oauthScopes: string[];
  headers: Record<string, JsonValue>;
  body: JsonValue;
  rawJson: string;
  error: string | null;
};
