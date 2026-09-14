import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {RelationshipsPage} from "./RelationshipsPage";

const person={personKey:"telegram:7:8:1",telegramUserId:1,displayName:"Alex",username:"alex",identityStatus:"UNMAPPED",buyerStatus:null,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-06T14:00:00Z",latestMessagePreview:"hello",activePurchaseIntent:false,activeSalesSession:false};
const response=(body:unknown)=>Promise.resolve(new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}}));
afterEach(()=>vi.restoreAllMocks());

it("takes over, sends a manual message, and returns control without losing list state",async()=>{
 let mode:"AVA_AUTO"|"HUMAN_OPERATOR"="AVA_AUTO",version=0;
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{const url=String(input);
  if(url.includes("/messages?")&&!init?.method)return response({person,items:[],olderCursor:null,hasMoreOlder:false});
  if(url.endsWith("/control"))return response({mode,controlVersion:version,changedAt:null,changedBy:"SYSTEM_DEFAULT",reason:null,lastManualActivityAt:null,activePurchaseIntent:true,activeSalesSession:false});
  if(url.endsWith("/takeover")){mode="HUMAN_OPERATOR";version++;return response({mode,controlVersion:version,activePurchaseIntent:true,activeSalesSession:false});}
  if(url.endsWith("/return-to-ava")){mode="AVA_AUTO";version++;return response({mode,controlVersion:version,activePurchaseIntent:true,activeSalesSession:false});}
  if(url.endsWith("/messages")&&init?.method==="POST")return response({state:"CONFIRMED",eventKey:"telegram:1:99",direction:"AVA",content:"operator reply",timestamp:"2026-09-06T14:02:00Z",telegramMessageId:99,messageType:"HUMAN_OPERATOR",purchaseIntentId:null,origin:"HUMAN_OPERATOR"});
  return response({items:[person],nextCursor:null,hasMore:false});
 });
 render(<RelationshipsPage/>);
 fireEvent.change(await screen.findByLabelText("Search chats"),{target:{value:"alex"}});
 fireEvent.click(screen.getByRole("button",{name:/Alex/}));
 fireEvent.click(await screen.findByRole("button",{name:"More conversation controls"}));
 fireEvent.click(screen.getByRole("menuitem",{name:"Take Over"}));
 expect(screen.getByRole("dialog")).toHaveTextContent("unresolved PurchaseIntent");
 fireEvent.click(screen.getByRole("dialog").querySelector("button:last-child")!);
 expect(await screen.findByText("MANUAL")).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText("Write a message"),{target:{value:"operator reply"}});
 fireEvent.click(screen.getByRole("button",{name:"Send"}));
 expect(await screen.findByText("operator reply")).toBeInTheDocument();
 const call=fetchMock.mock.calls.find(([input])=>String(input).endsWith("/messages"));
 expect(JSON.parse(String((call?.[1] as RequestInit).body))).toMatchObject({text:"operator reply",expectedControlVersion:1});
 fireEvent.click(screen.getByRole("button",{name:"More conversation controls"}));
 fireEvent.click(screen.getByRole("menuitem",{name:"Return to Ava"}));
 fireEvent.click(screen.getByRole("dialog").querySelector("button:last-child")!);
 await waitFor(()=>expect(screen.getByText("Ava Auto")).toBeInTheDocument());
 expect(screen.queryByLabelText("Write a message")).not.toBeInTheDocument();
 expect(screen.getByLabelText("Search chats")).toHaveValue("alex");
});
