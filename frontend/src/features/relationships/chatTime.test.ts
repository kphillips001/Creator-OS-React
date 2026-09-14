import {describe,expect,it} from "vitest";
import {formatChatCalendarDate,formatChatDay,formatChatTime,OPERATOR_TIME_ZONE} from "./chatTime";

describe("Business Chat operator time",()=>{
 it("renders a September Eastern 5:39 PM instant as Central 4:39 PM",()=>{const persisted="2026-09-13T21:39:00Z";expect(formatChatTime(persisted)).toBe("4:39 PM");expect(persisted).toBe("2026-09-13T21:39:00Z");});
 it("uses the Chicago IANA zone",()=>expect(OPERATOR_TIME_ZONE).toBe("America/Chicago"));
 it("handles the Chicago daylight-saving transition",()=>{expect(formatChatTime("2026-03-08T07:30:00Z")).toBe("1:30 AM");expect(formatChatTime("2026-03-08T08:30:00Z")).toBe("3:30 AM");});
 it("formats calendar days in operator time without changing the instant",()=>{const value="2026-09-14T04:30:00Z";expect(formatChatCalendarDate(value)).toBe("Sep 13, 2026");expect(formatChatDay(value,new Date("2026-09-14T05:00:00Z"))).toBe("YESTERDAY");expect(value).toBe("2026-09-14T04:30:00Z");});
});
