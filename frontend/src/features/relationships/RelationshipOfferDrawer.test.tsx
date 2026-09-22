import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import {RelationshipOfferDrawer} from "./RelationshipOfferDrawer";

const response=(body:unknown,status=200)=>Promise.resolve(new Response(JSON.stringify(body),{status,headers:{"Content-Type":"application/json"}}));
const control={mode:"HUMAN_OPERATOR" as const,controlVersion:4,changedAt:null,changedBy:"operator",reason:null,lastManualActivityAt:null,activePurchaseIntent:false,activeSalesSession:false};
const card={offeringId:"offer-1",title:"Midnight Set",description:"private",type:"SINGLE_IMAGE",priceMinor:2500,currency:"USD",thumbnailUrl:"/thumb",status:"AVAILABLE",owned:false,eligible:true,presentationCount:0,recommended:true,activePurchaseIntentId:null};
afterEach(()=>vi.restoreAllMocks());

describe("Relationship Content / Offer picker",()=>{
 it("defaults to recommended, hides purchased, reviews canonical price, and submits once",async()=>{
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input)=>{
   const url=String(input);
   if(url.includes("offer-inventory"))return response({items:[card],view:"RECOMMENDED",hidePurchased:true,businessConnectionId:"bc-1"});
   if(url.endsWith("/offers/prepare"))return response({offering:card,businessConnectionId:"bc-1",controlVersion:4,defaultMessage:"Picked for you"});
   if(url.endsWith("/offers"))return response({state:"CONFIRMED",eventKey:"telegram:3:9",direction:"AVA",content:"Picked for you",timestamp:"2026-09-09T20:00:00Z",telegramMessageId:9,messageType:"COMMERCIAL_OFFER",purchaseIntentId:"pi",origin:"HUMAN_OPERATOR"});
   return response({},404);
  });
  const sent=vi.fn();render(<RelationshipOfferDrawer personKey="telegram:1:2:3" control={control} onClose={()=>{}} onSent={sent}/>);
  const typeFilter=screen.getByLabelText("Offer type");
  expect(Array.from((typeFilter as HTMLSelectElement).options).map(option=>option.text)).toEqual(["All","Singles","Bundles"]);
  expect(screen.queryByRole("option",{name:"Sessions"})).not.toBeInTheDocument();
  expect(screen.getByLabelText("Offer view")).toHaveValue("RECOMMENDED");expect(screen.getByLabelText(/Hide purchased/)).toBeChecked();
  fireEvent.click(await screen.findByRole("button",{name:/Midnight Set/}));
  await screen.findByRole("heading",{name:"Review offer"});
  expect(screen.getByText(content=>content.includes("$25.00"))).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Send offer"}));
  await waitFor(()=>expect(sent).toHaveBeenCalledTimes(1));
  const sends=fetchMock.mock.calls.filter(([input])=>String(input).endsWith("/offers"));expect(sends).toHaveLength(1);
  expect(JSON.parse(String(sends[0]![1]!.body))).toMatchObject({offeringId:"offer-1",businessConnectionId:"bc-1",expectedControlVersion:4,text:"Picked for you"});
 });
 it("delegates route capability checks to canonical preparation without requiring Business",async()=>{
  const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("offer-inventory")
   ?response({items:[card],view:"RECOMMENDED",hidePurchased:true,businessConnectionId:null})
   :response({offering:card,businessConnectionId:null,controlVersion:4,defaultMessage:"Neutral offer"}));
  render(<RelationshipOfferDrawer personKey="key" control={control} onClose={()=>{}} onSent={()=>{}}/>);
  const button=await screen.findByRole("button",{name:/Midnight Set/});expect(button).toBeEnabled();fireEvent.click(button);
  await screen.findByRole("heading",{name:"Review offer"});
  const prepare=fetchMock.mock.calls.find(([input])=>String(input).endsWith("/offers/prepare"));
  expect(JSON.parse(String(prepare?.[1]?.body))).toMatchObject({businessConnectionId:null,expectedControlVersion:4});
 });
});

it("shows prospect ownership uncertainty and the actual delivery blocker",async()=>{
 vi.spyOn(globalThis,"fetch").mockImplementation(()=>response({items:[{...card,eligible:false,eligibilityReason:"No reachable transport supports the offer URL action",ownershipEvidence:"FANVUE_HISTORY_UNKNOWN"}],view:"RECOMMENDED",hidePurchased:true,businessConnectionId:null}));
 render(<RelationshipOfferDrawer personKey="prospect" control={control} onClose={()=>{}} onSent={()=>{}}/>);
 expect(await screen.findByText("No reachable transport supports the offer URL action")).toBeInTheDocument();
 expect(screen.getByText("Purchase history unavailable before account verification.")).toBeInTheDocument();
 expect(screen.getByRole("button",{name:/Midnight Set/})).toBeDisabled();
 expect(screen.queryByText("Verified customer conversation context is required.")).not.toBeInTheDocument();
});


it.each(["CONFIRMED","AMBIGUOUS","FAILED"])("keeps queued offers pending until %s evidence",async terminal=>{
 let release:((value:Response)=>void)|undefined;
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>{
  const url=String(input);
  if(url.includes("offer-inventory"))return response({items:[card],businessConnectionId:null});
  if(url.endsWith("/offers/prepare"))return response({offering:card,businessConnectionId:null,controlVersion:4,defaultMessage:"A photo"});
  if(url.endsWith("/offers"))return response({state:"PREPARED",operationId:"operation-one"});
  return new Promise<Response>(resolve=>{release=resolve});
 });
 const sent=vi.fn();render(<RelationshipOfferDrawer personKey="prospect" control={control} onClose={()=>{}} onSent={sent}/>);
 fireEvent.click(await screen.findByRole("button",{name:/Midnight Set/}));
 fireEvent.click(await screen.findByRole("button",{name:"Send offer"}));
 expect(await screen.findByText(/Offer queued/)).toBeInTheDocument();
 expect(sent).not.toHaveBeenCalled();
 expect(screen.getByLabelText("Offer message")).toBeDisabled();
 await waitFor(()=>expect(release).toBeDefined());
 release!(new Response(JSON.stringify({state:terminal,operationId:"operation-one",telegramMessageId:terminal==="CONFIRMED"?9:null,priceMinor:2499,currency:"USD",error:terminal==="FAILED"?"Peer unavailable before send":null}),{headers:{"Content-Type":"application/json"}}));
 if(terminal==="CONFIRMED")await waitFor(()=>expect(sent).toHaveBeenCalledTimes(1));
 else {expect(await screen.findByRole("alert")).toHaveTextContent(terminal==="AMBIGUOUS"?"Do not resend":"Peer unavailable");expect(sent).not.toHaveBeenCalled();}
 expect(fetchMock.mock.calls.filter(([input])=>String(input).endsWith("/offers"))).toHaveLength(1);
 expect(await screen.findByText("Final checkout price: $24.99")).toBeInTheDocument();
});
