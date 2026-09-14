import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import {RelationshipsPage} from "./RelationshipsPage";

const base={personKey:"telegram:7:8:1",telegramUserId:1,displayName:"Alex",username:"alex",identityStatus:"UNMAPPED",buyerStatus:null,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-13T19:00:00Z",latestMessagePreview:"hello",activePurchaseIntent:false,activeSalesSession:false,controlMode:"AVA_AUTO",needsAttention:false,isBuyer:false,operationalStatus:"NONE",operationalStatusReason:null,nextAutomaticAttemptAt:null,overdueSince:null,operationState:null,generationAttempts:0,sendAttempts:0,hasActiveClaim:false,attentionOccurrenceId:null,attentionAcknowledgedAt:null,attentionAcknowledgedBy:null} as const;
const response=(body:unknown)=>Promise.resolve(new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}}));
const list=(person:unknown,needsAttention=0)=>({items:[person],nextCursor:null,hasMore:false,summary:{total:1,needsAttention,buyers:0,prospects:1,manual:0,replyScheduled:0}});

afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});

describe("Chat operational status",()=>{
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
