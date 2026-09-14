import {fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {RelationshipsPage} from "./RelationshipsPage";

const person={personKey:"telegram:7:8:1",telegramUserId:1,displayName:"Stu",username:"stu",identityStatus:"UNMAPPED",buyerStatus:null,lifetimeVerifiedRevenueMinor:null,qualifyingPurchaseCount:null,latestActivityAt:"2026-09-13T20:00:00Z",latestMessagePreview:"hello",activePurchaseIntent:false,activeSalesSession:false,highValueProspect:false};
const intelligence={person,mappingStatus:"UNMAPPED",partial:true,operatorClassification:null,effectiveAttentionPriority:"HIGH",behavioralIntelligence:{buyingIntent:"NONE",currentSignal:"SEXUAL_ENGAGEMENT",salesStage:"PROSPECT"},customerValue:{buyerStatus:"UNMAPPED_PROSPECT",valueTier:"ENGAGED_PROSPECT",attentionTier:"HIGH",lifetimeSpendMinor:null,purchaseCount:null,repeatBuyer:false,relationshipLifecycle:"PROSPECT",relationshipInvestment:"STANDARD",continuationValue:"HIGH",timeWasterRisk:"NONE",retention:"NONE"},salesPerformance:{offersPresented:0,offersPurchased:0,offersNotPurchased:0,conversionRate:null,lastOffer:null,lastPurchase:null},commercialState:{activePurchaseIntent:null,activeSalesSession:null,activeOffer:null},purchaseHistory:[],relationshipIntelligence:{location:null,timezone:null,interests:[],pets:[],music:[],preferences:[]}};
const reply=(body:unknown)=>Promise.resolve(new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}}));
afterEach(()=>vi.restoreAllMocks());

it("renders compact ordered HVP badges and removes them only after confirmation",async()=>{
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,request={})=>{const url=String(input);if(url.includes("operator-classification")){const active=request.method!=="DELETE";return reply({intelligence:{...intelligence,operatorClassification:active?"HIGH_VALUE_PROSPECT":null,effectiveAttentionPriority:active?"PRIORITIZED":"HIGH"},scheduling:{scheduleAdvanced:active,advancedOperation:active?{operation_id:"fixture",next_retry_at:"2026-09-13T20:05:00Z"}:null}});}if(url.includes("/intelligence"))return reply(intelligence);if(url.includes("/messages?"))return reply({person,items:[],olderCursor:null,hasMoreOlder:false});if(url.includes("/control"))return reply({mode:"AVA_AUTO",controlVersion:0,activePurchaseIntent:false,activeSalesSession:false});return reply({items:[person],nextCursor:null,hasMore:false,summary:{total:1,needsAttention:0,buyers:0,prospects:1,manual:0}});});
 render(<RelationshipsPage/>);fireEvent.click(await screen.findByRole("button",{name:/Stu/}));
 await screen.findByRole("button",{name:"Open Customer Intelligence"});fireEvent.click(screen.getByRole("button",{name:"Open Customer Intelligence"}));
 const card=await screen.findByRole("region",{name:"Customer Intelligence"});
 expect(within(card).getByText("Engaged Prospect")).toBeInTheDocument();
 expect(within(card).getAllByText("Unverified").length).toBeGreaterThan(1);
 expect(within(card).getByText("Sexual Engagement")).toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"Close Customer Intelligence"}));
 expect(screen.queryByTitle("High Value Prospect")).not.toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"More conversation controls"}));let toggle=screen.getByRole("menuitem",{name:"High Value Prospect Off"});fireEvent.click(toggle);
 await waitFor(()=>expect(screen.getAllByTitle("High Value Prospect").some(node=>node.textContent==="HVP")).toBe(true));
 expect(screen.getByText("Prioritized")).toBeInTheDocument();
 const badges=screen.getAllByTitle("High Value Prospect");expect(badges.some(node=>node.textContent==="HVP")).toBe(true);
 const row=screen.getByRole("button",{name:/Stu/});expect(within(row).getByText("PROSPECT").nextElementSibling).toHaveTextContent("HVP");
 expect(row).not.toHaveTextContent("HIGH VALUE PROSPECT");
 fireEvent.click(screen.getByRole("button",{name:"More conversation controls"}));toggle=screen.getByRole("menuitem",{name:"High Value Prospect On"});fireEvent.click(toggle);await waitFor(()=>expect(within(row).queryByTitle("High Value Prospect")).not.toBeInTheDocument());
 expect(within(row).queryByTitle("High Value Prospect")).not.toBeInTheDocument();
 expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("operator-classification"),expect.objectContaining({method:"PUT"}));
 expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("operator-classification"),expect.objectContaining({method:"DELETE"}));
});

it("shows CUSTOMER only from authoritative buyer state",async()=>{const customer={...person,displayName:"Customer Name",isBuyer:true,identityStatus:"MAPPED_VERIFIED"};vi.spyOn(globalThis,"fetch").mockImplementation(input=>{const url=String(input);if(url.includes("/intelligence"))return reply({...intelligence,person:customer,mappingStatus:"VERIFIED"});if(url.includes("/messages?"))return reply({person:customer,items:[],olderCursor:null,hasMoreOlder:false});if(url.includes("/control"))return reply({mode:"AVA_AUTO",controlVersion:0,activePurchaseIntent:false,activeSalesSession:false});return reply({items:[customer],nextCursor:null,hasMore:false,summary:{total:1,needsAttention:0,buyers:1,prospects:0,manual:0}});});render(<RelationshipsPage/>);const row=await screen.findByRole("button",{name:/Customer Name/});expect(within(row).getByText("CUSTOMER")).toBeInTheDocument();fireEvent.click(row);expect(await screen.findAllByText("CUSTOMER")).toHaveLength(2);});
