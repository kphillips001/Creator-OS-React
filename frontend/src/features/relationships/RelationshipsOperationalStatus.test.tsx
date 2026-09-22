import {fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import {RelationshipsPage} from "./RelationshipsPage";

const base={personKey:"telegram:7:8:1",telegramUserId:1,displayName:"Alex",username:"alex",identityStatus:"UNMAPPED",buyerStatus:null,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-13T19:00:00Z",latestMessagePreview:"hello",activePurchaseIntent:false,activeSalesSession:false,controlMode:"AVA_AUTO",needsAttention:false,isBuyer:false,operationalStatus:"NONE",operationalStatusReason:null,nextAutomaticAttemptAt:null,overdueSince:null,operationState:null,generationAttempts:0,sendAttempts:0,hasActiveClaim:false,attentionOccurrenceId:null,attentionAcknowledgedAt:null,attentionAcknowledgedBy:null} as const;
const response=(body:unknown)=>Promise.resolve(new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}}));
const list=(person:unknown,needsAttention=0)=>({items:[person],nextCursor:null,hasMore:false,summary:{total:1,needsAttention,buyers:0,prospects:1,manual:0,replyScheduled:0}});

afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});

describe("Chat operational status",()=>{
 it("keeps LOW as the sole list classification and explains exhaustion in selected detail",async()=>{
  const person={...base,displayName:"Novi",marketTier:"LOW" as const,operationalStatus:"LOW_MARKET_LIMIT" as const,operationalStatusReason:"LOW_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED",repliesUsedToday:2,dailyReplyBudget:2,nextResetAt:"2026-09-14T05:00:00Z"};
  vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("/messages?")?response({person,items:[],olderCursor:null,hasMoreOlder:false}):String(input).endsWith("/control")?response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false}):response(list(person)));
  render(<RelationshipsPage/>);
  const row=await screen.findByRole("button",{name:/Novi/});
  expect(within(row).getByLabelText("Country Tier: Low")).toHaveTextContent("LOW");
  expect(row).toHaveTextContent("PROSPECT");
  expect(row).not.toHaveTextContent("LOW MARKET LIMIT");
  expect(row).not.toHaveTextContent(/DAILY LIMIT|CHAT LIMIT|REPLY LIMIT/);
  fireEvent.click(row);
  const detail=await screen.findByLabelText("Conversation operational status: Reply Limit Reached");
  expect(detail).toHaveTextContent("Reply Limit Reached");
  expect(detail).toHaveTextContent("Next eligible");
  expect(detail).toHaveTextContent("12:00 AM");
  expect(detail).toHaveTextContent("2 of 2 ordinary replies used today");
  expect(detail).not.toHaveTextContent("LOW_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED");
 });

 it("does not show a reply-limit state for LOW with remaining budget",async()=>{
  const person={...base,displayName:"Low Available",marketTier:"LOW" as const,repliesUsedToday:1,dailyReplyBudget:2,operationalStatus:"NONE" as const};
  vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("/messages?")?response({person,items:[],olderCursor:null,hasMoreOlder:false}):String(input).endsWith("/control")?response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false}):response(list(person)));
  render(<RelationshipsPage/>);const row=await screen.findByRole("button",{name:/Low Available/});
  expect(within(row).getByLabelText("Country Tier: Low")).toBeInTheDocument();
  expect(row).not.toHaveTextContent("Reply Limit Reached");fireEvent.click(row);
 expect(await screen.findByLabelText("Conversation operational status")).not.toHaveTextContent("Reply Limit Reached");
 });

 it("keeps the constrained LOW row compact without a redundant status placeholder",async()=>{
  Object.defineProperty(window,"innerWidth",{configurable:true,value:640});
  const person={...base,displayName:"Novi Zoom",marketTier:"LOW" as const,operationalStatus:"LOW_MARKET_LIMIT" as const,repliesUsedToday:2,dailyReplyBudget:2,nextResetAt:"2026-09-14T05:00:00Z"};
  vi.spyOn(globalThis,"fetch").mockImplementation(()=>response(list(person)));
  render(<RelationshipsPage/>);const row=await screen.findByRole("button",{name:/Novi Zoom/});
  expect(within(row).getAllByText(/PROSPECT|LOW/).map(node=>node.textContent)).toEqual(["PROSPECT","LOW"]);
  expect(row.querySelectorAll(".chat-badge")).toHaveLength(2);
 });

 it("renders conversation activity and transcript timestamps in the operator timezone",async()=>{
  const person={...base,latestActivityAt:"2026-09-13T21:39:00Z"};
  const messages=[{eventKey:"customer-central",direction:"CUSTOMER",content:"timezone check",timestamp:"2026-09-13T21:40:00Z",telegramMessageId:17,messageType:"ORDINARY_CHAT",purchaseIntentId:null}];
  vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("/messages?")?response({person,items:messages,olderCursor:null,hasMoreOlder:false}):String(input).endsWith("/control")?response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false}):response(list(person)));
  render(<RelationshipsPage/>);
  const row=await screen.findByRole("button",{name:/Alex/});
  expect(row).toHaveTextContent("4:39 PM");
  fireEvent.click(row);
  expect((await screen.findByText("timezone check")).closest("article")).toHaveTextContent("4:40 PM");
 });

 it("renders the authoritative scheduled time and selected detail",async()=>{
  const person={...base,operationalStatus:"REPLY_SCHEDULED",operationalStatusReason:"Waiting for Ava availability.",nextAutomaticAttemptAt:"2026-09-13T21:39:00Z",operationState:"RETRYABLE"};
  vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("/messages?")?response({person,items:[],olderCursor:null,hasMoreOlder:false}):String(input).endsWith("/control")?response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false}):response(list(person)));
  render(<RelationshipsPage/>);
  const row=await screen.findByRole("button",{name:/Alex/});
  expect(row).toHaveTextContent("REPLY SCHEDULED");
  fireEvent.click(row);
  expect(await screen.findByLabelText("Conversation operational status")).toHaveTextContent("Next reply");
  expect(screen.getByLabelText("Conversation operational status")).toHaveTextContent("4:39 PM");
  expect(person.nextAutomaticAttemptAt).toBe("2026-09-13T21:39:00Z");
  expect(screen.queryByRole("button",{name:"Acknowledge"})).not.toBeInTheDocument();
 expect(screen.queryByRole("button",{name:"Inspect & Resolve"})).not.toBeInTheDocument();
 });

 it("renders a highlighted ready badge with the exact persisted read-only preview",async()=>{
  const pending="Oh you noticed that one, huh? 😏 I had a feeling it might get your attention.";
  const person={...base,operationalStatus:"REPLY_READY" as const,operationalStatusReason:"Delivery retry scheduled.",nextAutomaticAttemptAt:"2026-09-13T21:39:00Z",operationState:"RETRYABLE",pendingReplyPreview:pending};
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(()=>response(list(person)));
  render(<RelationshipsPage/>);
  const row=await screen.findByRole("button",{name:/Alex/});
  const badge=within(row).getByText("REPLY READY · 4:39 PM");
  expect(badge).toHaveClass("is-reply_ready");
  const callsBeforeHover=fetchMock.mock.calls.length;
  fireEvent.mouseEnter(badge);
  const preview=await screen.findByRole("tooltip");
  expect(preview).toHaveTextContent("Ava's scheduled reply");
  expect(preview).toHaveTextContent(pending);
  fireEvent.mouseLeave(badge);
  fireEvent.focus(badge);
  expect(await screen.findByRole("tooltip")).toHaveTextContent(pending);
 expect(fetchMock).toHaveBeenCalledTimes(callsBeforeHover);
 });

 it("shows the exact pending reply in the selected conversation only when ready",async()=>{
  const pending="The exact persisted prepared reply.";
  const ready={...base,operationalStatus:"REPLY_READY" as const,operationalStatusReason:"Prepared for scheduled delivery.",nextAutomaticAttemptAt:"2026-09-13T21:39:00Z",operationState:"RETRYABLE",operationId:"33333333-3333-4333-8333-333333333333",inboundMessageId:99,pendingReplyPreview:pending};
  vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("/messages?")?response({person:ready,items:[],olderCursor:null,hasMoreOlder:false}):String(input).endsWith("/control")?response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false}):response(list(ready)));
  render(<RelationshipsPage/>);
  fireEvent.click(await screen.findByRole("button",{name:/Alex/}));
  const card=await screen.findByLabelText("Ava pending reply");
  expect(card).toHaveTextContent("AVA · PENDING REPLY");
  expect(card).toHaveTextContent("Scheduled for 4:39 PM");
  expect(card).toHaveTextContent(pending);
  expect(within(card).getByRole("button",{name:"Cancel Reply"})).toBeInTheDocument();
 });

 it("confirms and cancels only the exact ready reply while Ava Auto stays on",async()=>{
  let cancelled=false;
  const ready={...base,operationalStatus:"REPLY_READY" as const,nextAutomaticAttemptAt:"2026-09-13T21:39:00Z",operationState:"RETRYABLE",operationId:"11111111-1111-4111-8111-111111111111",inboundMessageId:77,pendingReplyPreview:"Persisted reply"};
  const normal={...ready,operationalStatus:"NONE" as const,nextAutomaticAttemptAt:null,operationState:"SUPPRESSED",operationId:null,inboundMessageId:null,pendingReplyPreview:null};
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{
   const url=String(input);
   if(url.endsWith("/cancel-reply")&&init?.method==="POST"){
    cancelled=true;
    expect(JSON.parse(String(init.body))).toEqual({operationId:ready.operationId,inboundMessageId:77});
    return response({operationId:ready.operationId,state:"SUPPRESSED",changed:true,reason:"OPERATOR_CANCELLED_PREPARED_REPLY"});
   }
   if(url.includes("/messages?"))return response({person:cancelled?normal:ready,items:[],olderCursor:null,hasMoreOlder:false});
   if(url.endsWith("/control"))return response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false});
   return response(list(cancelled?normal:ready));
  });
  render(<RelationshipsPage/>);
  const row=await screen.findByRole("button",{name:/Alex/});
  fireEvent.click(row);
  const pendingCard=await screen.findByLabelText("Ava pending reply");
  fireEvent.click(within(pendingCard).getByRole("button",{name:"Cancel Reply"}));
  const dialog=await screen.findByRole("dialog",{name:"Cancel Ava's reply?"});
  expect(dialog).toHaveTextContent("This prepared reply will not be sent. Ava Auto will remain on and will respond normally when the customer sends a new message.");
  expect(within(dialog).getByRole("button",{name:"Keep Reply"})).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button",{name:"Cancel Reply"}));
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/cancel-reply"),expect.objectContaining({method:"POST"})));
  await waitFor(()=>expect(screen.queryByText(/REPLY READY/)).not.toBeInTheDocument());
  expect(screen.queryByLabelText("Ava pending reply")).not.toBeInTheDocument();
 });

 it("surfaces a bounded non-JSON cancellation error instead of a JSON.parse exception",async()=>{
  const ready={...base,operationalStatus:"REPLY_READY" as const,nextAutomaticAttemptAt:"2026-09-13T21:39:00Z",operationState:"RETRYABLE",operationId:"22222222-2222-4222-8222-222222222222",inboundMessageId:88,pendingReplyPreview:"Persisted reply"};
  vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{
   const url=String(input);
   if(url.endsWith("/cancel-reply")&&init?.method==="POST")return Promise.resolve(new Response("Gateway unavailable",{status:502,headers:{"Content-Type":"text/plain"}}));
   if(url.includes("/messages?"))return response({person:ready,items:[],olderCursor:null,hasMoreOlder:false});
   if(url.endsWith("/control"))return response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false});
   return response(list(ready));
  });
  render(<RelationshipsPage/>);
  const row=await screen.findByRole("button",{name:/Alex/});
  fireEvent.mouseEnter(within(row).getByText(/REPLY READY/));
  fireEvent.click(await screen.findByRole("button",{name:"Cancel Reply"}));
  const dialog=await screen.findByRole("dialog",{name:"Cancel Ava's reply?"});
  fireEvent.click(within(dialog).getByRole("button",{name:"Cancel Reply"}));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Gateway unavailable");
  expect(dialog).not.toHaveTextContent("JSON.parse");
 });

 it("wraps a long ready preview and never leaks it into another conversation",async()=>{
  const longReply=`A long persisted reply ${"with enough detail to require wrapping ".repeat(20)}`;
  const ready={...base,personKey:"telegram:7:8:1",telegramUserId:1,displayName:"Ready Customer",operationalStatus:"REPLY_READY" as const,nextAutomaticAttemptAt:"2026-09-13T21:39:00Z",pendingReplyPreview:longReply};
  const scheduled={...base,personKey:"telegram:7:8:2",telegramUserId:2,displayName:"Scheduled Customer",operationalStatus:"REPLY_SCHEDULED" as const,nextAutomaticAttemptAt:"2026-09-13T21:45:00Z",pendingReplyPreview:null};
  vi.spyOn(globalThis,"fetch").mockImplementation(()=>response({items:[ready,scheduled],nextCursor:null,hasMore:false,summary:{total:2,needsAttention:0,buyers:0,prospects:2,manual:0,replyScheduled:2}}));
  render(<RelationshipsPage/>);
  const readyRow=await screen.findByRole("button",{name:/Ready Customer/});
  const scheduledRow=await screen.findByRole("button",{name:/Scheduled Customer/});
  expect(scheduledRow).toHaveTextContent("REPLY SCHEDULED");
  expect(within(scheduledRow).queryByText(/REPLY READY/)).not.toBeInTheDocument();
  fireEvent.mouseEnter(within(readyRow).getByText(/REPLY READY/));
  const preview=await screen.findByRole("tooltip");
  expect(preview).toHaveClass("reply-ready-preview");
  expect(preview.querySelector("p")?.textContent).toBe(longReply);
 });

 it("renders an authoritative overdue duration",async()=>{
  vi.setSystemTime(new Date("2026-09-13T20:10:00Z"));
  const person={...base,operationalStatus:"OVERDUE",operationalStatusReason:"Waiting for Ava availability.",nextAutomaticAttemptAt:"2026-09-13T20:02:00Z",overdueSince:"2026-09-13T20:04:00Z",operationState:"RETRYABLE"};
  vi.spyOn(globalThis,"fetch").mockImplementation(()=>response(list(person)));
  render(<RelationshipsPage/>);
  expect(await screen.findByRole("button",{name:/Alex/})).toHaveTextContent("OVERDUE · 6m");
 });

 it("acknowledges genuine attention and hides the action without sending a message",async()=>{
  const person={...base,needsAttention:true,operationalStatus:"NEEDS_ATTENTION",operationalStatusReason:"A required response could not pass the final quality check.",operationState:"SUPPRESSED",attentionOccurrenceId:"occurrence-token"};
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{
   const url=String(input);
   if(url.includes("/messages?")&&!init?.method)return response({person,items:[],olderCursor:null,hasMoreOlder:false});
   if(url.endsWith("/control"))return response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false});
   if(url.includes("/attention/")&&init?.method==="POST")return response({...person,operationalStatus:"NONE",needsAttention:false,attentionAcknowledgedAt:"2026-09-13T20:00:00Z",attentionAcknowledgedBy:"CREATOR_OS_OPERATOR"});
   return response(list(person,1));
  });
  render(<RelationshipsPage/>);
  fireEvent.click(await screen.findByRole("button",{name:/Alex/}));
  expect(await screen.findByRole("button",{name:"Inspect & Resolve"})).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("button",{name:"Acknowledge"}));
  await waitFor(()=>expect(screen.queryByRole("button",{name:"Acknowledge"})).not.toBeInTheDocument());
  const mutation=fetchMock.mock.calls.find(([input,init])=>String(input).includes("/attention/")&&init?.method==="POST");
  expect(String(mutation?.[0])).toContain("occurrence-token/acknowledge");
  expect(fetchMock.mock.calls.some(([input,init])=>String(input).endsWith("/messages")&&init?.method==="POST")).toBe(false);
 });

 it("polls every twenty seconds without overlap and stops after unmount",async()=>{
  vi.useFakeTimers();
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(()=>response(list(base)));
  const view=render(<RelationshipsPage/>);
  await vi.runAllTicks();
  await vi.advanceTimersByTimeAsync(20000);
  expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  const beforeUnmount=fetchMock.mock.calls.length;
  view.unmount();
  await vi.advanceTimersByTimeAsync(40000);
  expect(fetchMock).toHaveBeenCalledTimes(beforeUnmount);
 });
});


it.each([['SYSTEM_INCIDENT','SYSTEM INCIDENT'],['DELIVERY_UNCERTAIN','DELIVERY UNCERTAIN'],['RECOVERY_PENDING','RECOVERY PENDING']])(
 "renders %s separately from human attention",async(status,label)=>{
 const person={...base,operationalStatus:status,operationalCategory:status,needsAttention:false};
 vi.spyOn(globalThis,"fetch").mockImplementation(()=>response(list(person)));
 render(<RelationshipsPage/>);const row=await screen.findByRole('button',{name:/Alex/});
 expect(row).toHaveTextContent(label);expect(row).not.toHaveTextContent('NEEDS ATTENTION');
});
