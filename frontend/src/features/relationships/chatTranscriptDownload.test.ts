import { describe, expect, it, vi } from "vitest";
import { buildChatTranscript, saveChatTranscript, transcriptFilename } from "./chatTranscriptDownload";
import { relationshipsApi } from "./api";

const person = { displayName: "Joseph / Test", username: "jo_seph" };
const messages: any[] = [
  { eventKey: "new", direction: "AVA", content: "Line one\nLine two 😊", timestamp: "2026-09-15T14:01:00-05:00", operationId: "secret-operation" },
  { eventKey: "old", direction: "CUSTOMER", content: "Ça va — it’s good", timestamp: "2026-09-15T13:59:00-05:00", diagnostics: "hidden" },
];

describe("customer-visible chat transcript download", () => {
  it("exports chronological visible text with timestamps, multiline, and Unicode", () => {
    const value = buildChatTranscript(person as any, messages, new Date("2026-09-15T19:00:00Z"));
    expect(value).toContain("Creator-OS Chat Transcript");
    expect(value).toContain("Relationship: Joseph / Test");
    expect(value).toContain("Username: @jo_seph");
    expect(value.indexOf("CUSTOMER:\nÇa va — it’s good")).toBeLessThan(value.indexOf("AVA:\nLine one\nLine two 😊"));
    expect(value).not.toContain("secret-operation");
    expect(value).not.toContain("diagnostics");
    expect(value).not.toMatch(/Ã¢|â‚¬/);
  });

  it("creates a safe TXT filename without internal identifiers", () => {
    expect(transcriptFilename("Joseph / Test", new Date("2026-09-15T19:00:00Z")))
      .toBe("creator-os-chat-joseph-test-2026-09-15.txt");
  });

  it("uses a UTF-8 text Blob and revokes its temporary URL", () => {
    const create = vi.fn(() => "blob:test");
    const revoke = vi.fn();
    Object.defineProperties(URL, {
      createObjectURL: { configurable: true, value: create },
      revokeObjectURL: { configurable: true, value: revoke },
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    saveChatTranscript("chat.txt", "emoji 😊");
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ type: "text/plain;charset=utf-8" }));
    expect(click).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:test");
  });

  it("retrieves every canonical transcript page rather than the viewport page", async () => {
    const response = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const older = String(input).includes("cursor=older");
      return response({
        person, items: [older ? messages[1] : messages[0]],
        olderCursor: older ? null : "older", hasMoreOlder: !older,
      });
    });
    const result = await relationshipsApi.completeMessages("telegram:2:2:1");
    expect(result.map((item) => item.eventKey)).toEqual(["old", "new"]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
