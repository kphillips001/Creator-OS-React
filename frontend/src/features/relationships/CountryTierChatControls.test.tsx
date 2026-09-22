import {fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {RelationshipsPage} from "./RelationshipsPage";
import type {MarketTier,Relationship} from "./api";

const people:Relationship[]=[
 {personKey:"telegram:2:2:1",telegramUserId:1,displayName:"Novi Fixture",username:null,identityStatus:"UNMAPPED",buyerStatus:null,isBuyer:false,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-14T20:01:00Z",latestMessagePreview:"one",activePurchaseIntent:false,activeSalesSession:false,controlMode:"AVA_AUTO",marketTier:"LOW"},
 {personKey:"telegram:2:2:2",telegramUserId:2,displayName:"Miroslav Fixture",username:null,identityStatus:"UNMAPPED",buyerStatus:null,isBuyer:false,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-14T20:02:00Z",latestMessagePreview:"two",activePurchaseIntent:false,activeSalesSession:false,controlMode:"AVA_AUTO",marketTier:"MEDIUM",highValueProspect:true},
 {personKey:"telegram:2:2:3",telegramUserId:3,displayName:"Buyer Fixture",username:null,identityStatus:"MAPPED_VERIFIED",buyerStatus:"VERIFIED_BUYER",isBuyer:true,lifetimeVerifiedRevenueMinor:100,qualifyingPurchaseCount:1,latestActivityAt:"2026-09-14T20:03:00Z",latestMessagePreview:"three",activePurchaseIntent:false,activeSalesSession:false,controlMode:"AVA_AUTO",marketTier:"HIGH"},
 {personKey:"telegram:2:2:4",telegramUserId:4,displayName:"Unclassified Fixture",username:null,identityStatus:"UNMAPPED",buyerStatus:null,isBuyer:false,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-14T20:04:00Z",latestMessagePreview:"four",activePurchaseIntent:false,activeSalesSession:false,controlMode:"AVA_AUTO",marketTier:"UNCLASSIFIED"},
];
const ok=(body:unknown)=>Promise.resolve(new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}}));
function mock(){return vi.spyOn(globalThis,"fetch").mockImplementation(input=>{const url=new URL(String(input),"http://local");if(url.pathname.endsWith("/messages"))return ok({person:people[1],items:[],olderCursor:null,hasMoreOlder:false});if(url.pathname.endsWith("/control"))return ok({mode:"AVA_AUTO",controlVersion:0,activePurchaseIntent:false,activeSalesSession:false});if(url.pathname.endsWith("/market-tier"))return ok({marketTier:"MEDIUM",effectiveProspectInvestment:"STANDARD",highValueProspect:true,verifiedBuyer:false,repliesUsedToday:0,dailyReplyBudget:5,budgetStatus:"AVAILABLE",nextBudgetResetAt:null,prospectReplyLimit:null});if(url.pathname.endsWith("/intelligence"))return ok({person:people[1],mappingStatus:"UNMAPPED",partial:true,operatorClassification:"HIGH_VALUE_PROSPECT",effectiveAttentionPriority:"PRIORITIZED",behavioralIntelligence:{buyingIntent:"NONE",currentSignal:"NONE",salesStage:"PROSPECT"},customerValue:{buyerStatus:"UNMAPPED_PROSPECT",valueTier:"PROSPECT",attentionTier:"STANDARD",lifetimeSpendMinor:null,purchaseCount:null,repeatBuyer:false,relationshipLifecycle:"PROSPECT",relationshipInvestment:"STANDARD",continuationValue:"STANDARD",timeWasterRisk:"NONE",retention:"NONE"},salesPerformance:{offersPresented:0,offersPurchased:0,offersNotPurchased:0,conversionRate:null,lastOffer:null,lastPurchase:null},commercialState:{activePurchaseIntent:null,activeSalesSession:null,activeOffer:null},purchaseHistory:[],relationshipIntelligence:{location:null,timezone:null,interests:[],pets:[],music:[],preferences:[]}});const tiers=url.searchParams.getAll("countryTier") as MarketTier[];const visible=tiers.length?people.filter(person=>tiers.includes(person.marketTier||"UNCLASSIFIED")):people;return ok({items:visible,nextCursor:null,hasMore:false,sort:url.searchParams.get("sort"),filter:url.searchParams.get("filter"),countryTiers:tiers,summary:{total:4,needsAttention:0,buyers:1,prospects:3,manual:0}});});}
afterEach(()=>vi.restoreAllMocks());

it("labels Country Tier distinctly, keeps compact accessible badges, and preserves unclassified",async()=>{
 mock();render(<RelationshipsPage/>);await screen.findByText("Novi Fixture");
 expect(screen.getByLabelText("Country Tier: Low")).toHaveTextContent("LOW");
 const miro=screen.getByText("Miroslav Fixture").closest("button")!;
 expect(within(miro).getByLabelText("Country Tier: Medium")).toHaveTextContent("MED");
 expect(within(miro).getByTitle("High Value Prospect")).toHaveTextContent("HVP");
 expect(within(screen.getByText("Unclassified Fixture").closest("button")!).queryByLabelText(/Country Tier/)).not.toBeInTheDocument();
 fireEvent.click(miro);fireEvent.click(await screen.findByRole("button",{name:"Classify relationship"}));
 const classify=screen.getByRole("menu",{name:"Classify relationship"});
 expect(within(classify).getByText("Country Tier")).toBeInTheDocument();
 for(const name of ["HIGH","MED","LOW","UNCLASSIFIED"])expect(within(classify).getByRole("menuitem",{name})).toBeInTheDocument();
 expect(within(classify).getByRole("menuitem",{name:"MED"})).toHaveAttribute("aria-pressed","true");
 expect(within(classify).getByRole("menuitem",{name:"High Value Prospect: ON"})).toBeInTheDocument();
});

it("offers both authoritative Country Tier sorts",async()=>{
 const fetchMock=mock();render(<RelationshipsPage/>);await screen.findByText("Novi Fixture");const sort=screen.getByRole("combobox",{name:"Sort chats"});
 expect(within(sort).getByRole("option",{name:"Country Tier — High to Low"})).toBeInTheDocument();
 expect(within(sort).getByRole("option",{name:"Country Tier — Low to High"})).toBeInTheDocument();
 fireEvent.change(sort,{target:{value:"COUNTRY_TIER_HIGH_TO_LOW"}});
 await waitFor(()=>expect(fetchMock.mock.calls.some(([url])=>String(url).includes("sort=COUNTRY_TIER_HIGH_TO_LOW"))).toBe(true));
});

it("multi-selects canonical tiers and composes them with search and primary filters",async()=>{
 const fetchMock=mock();render(<RelationshipsPage/>);await screen.findByText("Novi Fixture");
 fireEvent.click(screen.getByRole("button",{name:"More chat filters"}));let menu=screen.getByRole("menu",{name:"More chat filters"});
 fireEvent.click(within(menu).getByRole("menuitemcheckbox",{name:/HIGH/}));
 await waitFor(()=>expect(screen.queryByText("Novi Fixture")).not.toBeInTheDocument());
 fireEvent.click(within(menu).getByRole("menuitemcheckbox",{name:/MED/}));
 await waitFor(()=>expect(screen.getByRole("button",{name:"More chat filters"})).toHaveTextContent("(2)"));
 fireEvent.click(screen.getByRole("button",{name:"Prospects"}));
 await waitFor(()=>expect(fetchMock.mock.calls.some(([url])=>String(url).includes("filter=PROSPECTS"))).toBe(true));
 const search=screen.getByRole("textbox",{name:"Search chats"});fireEvent.change(search,{target:{value:"Miroslav"}});fireEvent.submit(search.closest("form")!);
 await waitFor(()=>expect(fetchMock.mock.calls.some(([url])=>{const value=String(url);return value.includes("filter=PROSPECTS")&&value.includes("search=Miroslav")&&value.includes("countryTier=HIGH")&&value.includes("countryTier=MEDIUM");})).toBe(true));
 expect(within(menu).getByRole("menuitemcheckbox",{name:/HIGH/})).toHaveAttribute("aria-checked","true");
 expect(within(menu).getByRole("menuitemcheckbox",{name:/MED/})).toHaveAttribute("aria-checked","true");
});

it("keeps the filter popover portaled and usable in a constrained viewport",async()=>{
 Object.defineProperty(window,"innerWidth",{configurable:true,value:640});Object.defineProperty(window,"innerHeight",{configurable:true,value:520});mock();render(<RelationshipsPage/>);await screen.findByText("Novi Fixture");
 fireEvent.click(screen.getByRole("button",{name:"More chat filters"}));const menu=screen.getByRole("menu",{name:"More chat filters"});
 expect(menu.parentElement).toBe(document.body);expect(within(menu).getByRole("menuitemcheckbox",{name:/UNCLASSIFIED/})).toBeInTheDocument();
});
