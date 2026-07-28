import type { JsonValue } from "../fanvue-api-explorer/types";

export type FanvueWebhookMonitorItem = {
  monitorId: string;
  timestamp: string;
  requestPath: string;
  payloadSize: number;
  payload: JsonValue;
  rawJson: string;
  headers: Record<string, JsonValue>;
  signatureHeaders: Record<string, JsonValue>;
  eventName: string;
  eventId: string | null;
  httpStatus: number;
  signatureValid: boolean | null;
  processingResult: JsonValue;
  normalizationResult: JsonValue;
  persistenceResult: JsonValue;
  deliveryMetadata: JsonValue;
  exception: string | null;
  durationMs: number;
  retryCount: number | null;
};

export type FanvueWebhookMonitorResponse = {
  items: FanvueWebhookMonitorItem[];
  lastWebhookReceived: string | null;
  storage: "process-memory";
  limit: number;
};
