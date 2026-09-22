import {fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {RelationshipsPage} from "./RelationshipsPage";

const base={personKey:"telegram:7:8:1",telegramUserId:1,displayName:"Alex",username:"alex",identityStatus:"UNMAPPED",buyerStatus:null,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-13T19:00:00Z",latestMessagePreview:"hello",activePurchaseIntent:false,activeSalesSession:false,controlMode:"AVA_AUTO",needsAttention:false,isBuyer:false,operationalStatus:"NONE",operationalStatusReason:null,nextAutomaticAttemptAt:null,overdueSince:null,operationState:null,generationAttempts:0,sendAttempts:0,hasActiveClaim:false,attentionOccurrenceId:null,attentionAcknowledgedAt:null,attentionAcknowledgedBy:null} as const;
const response=(body:unknown)=>Promise.resolve(new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}}));
const list=(person:unknown,needsAttention=0)=>({items:[person],nextCursor:null,hasMore:false,summary:{total:1,needsAttention,buyers:0,prospects:1,manual:0,replyScheduled:0}});

afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});

it("badge click confirms; cancel does not write", async()=>{
 const person={...base,operationalStatus:"DELIVERY_UNCERTAIN",attentionOccurrenceId:"a"};
 const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(()=>response(list(person)));
 render(<RelationshipsPage/>);
 fireEvent.click(await screen.findByRole("button",{name:"Dismiss Delivery Uncertain warning"}));
 expect(screen.getByRole("dialog",{name:"Dismiss Delivery Uncertain?"})).toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"Cancel"}));
 expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
 expect(fetch.mock.calls.some(([url])=>String(url).includes("/acknowledge"))).toBe(false);
});

it("detail dismissal persists and remains hidden on refresh",async()=>{
 let dismissed=false;
 const person=()=>({...base,operationalStatus:dismissed?"NONE":"DELIVERY_UNCERTAIN",attentionOccurrenceId:dismissed?null:"a",deliveryCertainty:"UNKNOWN",deliveryUncertaintyAcknowledged:dismissed});
 const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(input=>{
  const url=String(input);
  if(url.endsWith("/acknowledge")){dismissed=true;return response(person());}
  if(url.includes("/messages?"))return response({person:person(),items:[],olderCursor:null,hasMoreOlder:false});
  if(url.endsWith("/control"))return response({mode:"AVA_AUTO",controlVersion:1,activePurchaseIntent:false,activeSalesSession:false});
  return response(list(person()));
 });
 const view=render(<RelationshipsPage/>);
 fireEvent.click(await screen.findByRole("button",{name:/Alex/}));
 const detail=await screen.findByLabelText("Conversation operational status");
 fireEvent.click(within(detail).getByRole("button",{name:"Dismiss Delivery Uncertain warning"}));
 fireEvent.click(screen.getByRole("button",{name:"Dismiss"}));
 await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
 expect(screen.getByText("Delivery Uncertain — Acknowledged")).toBeInTheDocument();
 expect(fetch.mock.calls.filter(([url])=>String(url).endsWith("/attention/a/acknowledge"))).toHaveLength(1);
 view.unmount();render(<RelationshipsPage/>);
 await screen.findByRole("button",{name:/Alex/});
 expect(screen.queryByRole("button",{name:"Dismiss Delivery Uncertain warning"})).not.toBeInTheDocument();
});

it("failed acknowledgement retains warning",async()=>{
 const person={...base,operationalStatus:"DELIVERY_UNCERTAIN",attentionOccurrenceId:"a"};
 vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).endsWith("/acknowledge")?Promise.resolve(new Response(JSON.stringify({detail:"Occurrence changed"}),{status:409})):response(list(person)));
 render(<RelationshipsPage/>);
 fireEvent.click(await screen.findByRole("button",{name:"Dismiss Delivery Uncertain warning"}));
 fireEvent.click(screen.getByRole("button",{name:"Dismiss"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("Occurrence changed");
 expect(screen.getByRole("button",{name:"Dismiss Delivery Uncertain warning"})).toBeInTheDocument();
});

