import {fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {RelationshipsPage} from "./RelationshipsPage";

const person={personKey:"telegram:7:8:1",telegramUserId:1,displayName:"Fixture",username:"fixture",identityStatus:"UNMAPPED",buyerStatus:null,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-13T20:00:00Z",latestMessagePreview:"hello",activePurchaseIntent:false,activeSalesSession:false,controlMode:"AVA_AUTO",operationalStatus:"NONE",ignored:false};
const intelligence={person,mappingStatus:"UNMAPPED",partial:true,operatorClassification:null,effectiveAttentionPriority:"HIGH",behavioralIntelligence:{buyingIntent:"DIRECT",currentSignal:"COMMERCIAL",salesStage:"PROSPECT"},customerValue:{buyerStatus:"UNMAPPED_PROSPECT",valueTier:"ENGAGED_PROSPECT",attentionTier:"HIGH",lifetimeSpendMinor:null,purchaseCount:null,repeatBuyer:false,relationshipLifecycle:"PROSPECT",relationshipInvestment:"STANDARD",continuationValue:"HIGH",timeWasterRisk:"NONE",retention:"NONE"},salesPerformance:{offersPresented:0,offersPurchased:0,offersNotPurchased:0,conversionRate:null,lastOffer:null,lastPurchase:null},commercialState:{activePurchaseIntent:null,activeSalesSession:null,activeOffer:null},purchaseHistory:[],relationshipIntelligence:{location:null,timezone:null,interests:[],pets:[],music:[],preferences:[]}};
const control=(ignored:boolean,version:number)=>({mode:"AVA_AUTO",controlVersion:version,communicationDisposition:ignored?"IGNORED":"ACTIVE",ignored,ignoreVersion:ignored?1:2,ignoredAt:null,ignoredBy:null,unignoredAt:null,unignoredBy:null,resumeAfterInboundMessageId:55,changedAt:null,changedBy:"test",reason:null,lastManualActivityAt:null,activePurchaseIntent:false,activeSalesSession:false});
const response=(body:unknown)=>Promise.resolve(new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}}));

afterEach(()=>vi.restoreAllMocks());

it("confirms Ignore, projects IGNORED everywhere, and unignores without a backlog release",async()=>{
 let ignored=false,version=0;
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init={})=>{const url=String(input);if(url.endsWith("/ignore")){ignored=init.method==="PUT";version+=1;return response(control(ignored,version));}if(url.includes("/messages?"))return response({person,items:[{eventKey:"1",direction:"CUSTOMER",content:"hello",timestamp:"2026-09-13T20:00:00Z",telegramMessageId:55,messageType:"ORDINARY_CHAT",purchaseIntentId:null}],olderCursor:null,hasMoreOlder:false});if(url.includes("/control"))return response(control(false,0));if(url.includes("/intelligence"))return response(intelligence);if(url.includes("/market-tier"))return response({marketTier:"HIGH",effectiveProspectInvestment:"HIGH",highValueProspect:true,verifiedBuyer:true,repliesUsedToday:0,dailyReplyBudget:"FULL",budgetStatus:"AVAILABLE",nextBudgetResetAt:null,prospectReplyLimit:null});const ignoredView=url.includes("filter=IGNORED");const visible=ignoredView?ignored:!ignored;return response({items:visible?[{...person,ignored,communicationDisposition:ignored?"IGNORED":"ACTIVE",highValueProspect:true,marketTier:"HIGH"}]:[],nextCursor:null,hasMore:false,summary:{total:ignored?0:1,needsAttention:0,buyers:0,prospects:ignored?0:1,manual:0,ignored:ignored?1:0}});});
 render(<RelationshipsPage/>);fireEvent.click(await screen.findByRole("button",{name:/Fixture/}));
 fireEvent.click(await screen.findByRole("button",{name:"More conversation controls"}));const ignore=screen.getByRole("menuitem",{name:"Ignore Relationship"});fireEvent.click(ignore);
 const dialog=screen.getByRole("dialog");expect(dialog).toHaveTextContent("Ava will stop communicating");expect(dialog).toHaveTextContent("remain visible but unanswered");fireEvent.click(within(dialog).getByRole("button",{name:"Ignore"}));
 await waitFor(()=>expect(screen.getByText("IGNORED")).toBeInTheDocument());
 expect(screen.getAllByText("IGNORED").length).toBeGreaterThan(0);expect(screen.getByRole("region",{name:"Conversation operational status"})).toHaveTextContent("Automatic communication disabled for this relationship.");
 expect(screen.queryByRole("button",{name:/Fixture.*HVP/i})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"More chat filters"}));fireEvent.click(screen.getByRole("menuitemradio",{name:"Ignored"}));
 await waitFor(()=>expect(screen.getByRole("button",{name:/Fixture.*HVP/i})).toBeInTheDocument());
 fireEvent.click(screen.getByRole("button",{name:"Open Customer Intelligence"}));expect(await screen.findByText("Communication Status")).toBeInTheDocument();expect(screen.getAllByText("Ignored").length).toBeGreaterThan(0);
 fireEvent.click(screen.getByRole("button",{name:"Close Customer Intelligence"}));fireEvent.click(screen.getByRole("button",{name:"More conversation controls"}));fireEvent.click(screen.getByRole("menuitem",{name:"Unignore Relationship"}));const unignore=screen.getByRole("dialog");expect(unignore).toHaveTextContent("will not receive automatic responses");fireEvent.click(within(unignore).getByRole("button",{name:"Unignore"}));
 await waitFor(()=>expect(screen.queryByText("IGNORED")).not.toBeInTheDocument());
 await waitFor(()=>expect(screen.queryByRole("button",{name:/Fixture.*HVP/i})).not.toBeInTheDocument());
 fireEvent.click(screen.getByRole("button",{name:"All"}));
 await waitFor(()=>expect(screen.getByRole("button",{name:/Fixture.*HVP/i})).toBeInTheDocument());
 expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/ignore"),expect.objectContaining({method:"PUT"}));expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/ignore"),expect.objectContaining({method:"DELETE"}));
});
