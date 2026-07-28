import type { JsonValue } from "./types";

export type EarningsDisplayResult = {
  body: JsonValue;
  sortingApplied: boolean;
};

export function sortEarningsForDisplay(
  endpoint: string,
  body: JsonValue,
): EarningsDisplayResult {
  if (
    endpoint !== "/insights/earnings"
    || body === null
    || Array.isArray(body)
    || typeof body !== "object"
    || !Array.isArray(body.data)
    || body.data.length < 2
  ) {
    return { body, sortingApplied: false };
  }

  const datedItems = body.data.map((item) => {
    if (
      item === null
      || Array.isArray(item)
      || typeof item !== "object"
      || typeof item.date !== "string"
    ) {
      return null;
    }
    const timestamp = Date.parse(item.date);
    return Number.isNaN(timestamp) ? null : { item, timestamp };
  });
  if (datedItems.some((item) => item === null)) {
    return { body, sortingApplied: false };
  }

  const sortedData = [...datedItems]
    .sort((left, right) => right!.timestamp - left!.timestamp)
    .map((entry) => entry!.item);
  return {
    body: { ...body, data: sortedData },
    sortingApplied: true,
  };
}
