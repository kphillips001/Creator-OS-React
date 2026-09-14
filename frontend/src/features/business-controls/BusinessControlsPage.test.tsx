import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";

import { BusinessControlsPage, effectiveMode } from "./BusinessControlsPage";
import type { CustomerControls, CustomerInventoryItem, GlobalControls } from "./api";

const globalState: GlobalControls = {
  avaBot: { desired: "OFF", effective: "OFF", reason: "Ava Bot is off." },
  contentSellingEnabled: true,
  sessionSellingEnabled: false,
};
const person: CustomerInventoryItem = {
  rowKey: "telegram:7:8:1", rowKind: "TELEGRAM_PROSPECT", relationshipKey: "telegram:7:8:1", hasConversation: true,
  personKey: "telegram:7:8:1", telegramUserId: 1, localFanvueUserId: 44, displayName: "Alex", username: "alex",
  identityStatus: "VERIFIED", buyerStatus: "BUYER", lifetimeVerifiedRevenueMinor: 5000,
  qualifyingPurchaseCount: 2, latestActivityAt: "2026-09-11T12:00:00Z",
  activePurchaseIntent: true, activeSalesSession: true, isBuyer: true,
  metadataComplete: true, providerEvidenceAvailable: false, platforms: { fanvue: "CANONICAL", telegram: "VERIFIED", x: "NOT_OBSERVED" },
  commerce: { lifetimeGrossMinor: 5000, lifetimeNetMinor: 4000, purchaseCount: 2, firstPurchaseAt: null, lastPurchaseAt: null, lastSyncedAt: null },
  controlAvailability: "AVAILABLE", controls: { avaChatEnabled: true, contentSellingEnabled: false, sessionSellingEnabled: false }, xNumericId: null,
};
const customerState = (overrides: Partial<CustomerControls["configured"]> = {}, globalOverrides: Partial<CustomerControls["global"]> = {}): CustomerControls => {
  const configured = { avaChatEnabled: true, contentSellingEnabled: false, sessionSellingEnabled: false, relationshipMode: "AVA_AUTO" as const, controlVersion: 3, ...overrides };
  const global = { avaBotDesired: "ON" as const, avaBotEffective: "ON" as const, contentSellingEnabled: true, sessionSellingEnabled: true, ...globalOverrides };
  return {
    identity: { telegramUserId: 1, telegramChatId: 1 }, configured, global,
    effective: {
      chatAllowed: configured.avaChatEnabled && global.avaBotEffective === "ON", chatReason: null,
      contentSellingAllowed: configured.contentSellingEnabled && global.contentSellingEnabled,
      contentSellingReason: configured.contentSellingEnabled && !global.contentSellingEnabled ? "GLOBAL_CONTENT_SELLING_DISABLED" : configured.contentSellingEnabled ? null : "CUSTOMER_CONTENT_SELLING_DISABLED",
      sessionSellingAllowed: configured.sessionSellingEnabled && global.sessionSellingEnabled,
      sessionSellingReason: configured.sessionSellingEnabled && !global.sessionSellingEnabled ? "GLOBAL_SESSION_SELLING_DISABLED" : configured.sessionSellingEnabled ? null : "CUSTOMER_SESSION_SELLING_DISABLED",
    },
  };
};
const response = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

afterEach(() => vi.restoreAllMocks());

describe("Business Controls", () => {
  it("loads authoritative global controls and preserves stored selling settings while Ava is off", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(globalState));
    render(<MemoryRouter><BusinessControlsPage/></MemoryRouter>);
    expect(await screen.findByText("AVA BOT")).toBeInTheDocument();
    expect(screen.getByLabelText("CONTENT SELLING control").querySelector('[aria-pressed="true"]')).toHaveTextContent("ON");
    expect(screen.getAllByText("Will apply when Ava Bot is turned on.")).toHaveLength(2);
  });

  it("shows ATTENTION without falsely presenting Ava Bot as on and links to technical details", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ ...globalState, avaBot: { desired: "ON", effective: "ATTENTION", reason: "Worker unavailable." } }));
    render(<MemoryRouter><BusinessControlsPage/></MemoryRouter>);
    expect(await screen.findByText("ATTENTION")).toBeInTheDocument();
    expect(screen.getByText("Ava is not fully operational.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View technical details/ })).toHaveAttribute("href", "/business/operations");
  });

  it("uses authoritative post-write global state and blocks duplicate logical mutations", async () => {
    let resolveWrite!: (value: Response) => void;
    const write = new Promise<Response>((resolve) => { resolveWrite = resolve; });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => init?.method === "PATCH" ? write : response(globalState));
    render(<MemoryRouter><BusinessControlsPage/></MemoryRouter>);
    const off = (await screen.findByLabelText("CONTENT SELLING control")).querySelectorAll("button")[0]!;
    fireEvent.click(off); fireEvent.click(off);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    resolveWrite(await response({ state: { ...globalState, contentSellingEnabled: false } }));
    await waitFor(() => expect(off).toHaveAttribute("aria-pressed", "true"));
  });

  it("does not display a failed global mutation as successful", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => init?.method === "PATCH" ? response({ detail: "Write rejected." }, 409) : response(globalState));
    render(<MemoryRouter><BusinessControlsPage/></MemoryRouter>);
    const control = await screen.findByLabelText("CONTENT SELLING control");
    fireEvent.click(control.querySelectorAll("button")[0]!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Write rejected.");
    expect(control.querySelector('[aria-pressed="true"]')).toHaveTextContent("ON");
  });

  it("loads, searches, selects, and mutates customer controls through canonical APIs", async () => {
    const initial = customerState();
    const enabled = customerState({ contentSellingEnabled: true });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.includes("customer-controls-inventory") ) return response({ items: [person], total: 1, page: 1, pageSize: 100 });
      if (init?.method === "PATCH") return response({ state: enabled });
      return response(initial);
    });
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    const search = await screen.findByLabelText("Search customers");
    fireEvent.change(search, { target: { value: "alex" } }); fireEvent.submit(search.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("search=alex"), expect.anything()));
    fireEvent.click(await screen.findByRole("row", { name: /Alex/ }));
    fireEvent.click((await screen.findByLabelText("CONTENT SELLING customer control")).querySelectorAll("button")[1]!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/automation-controls/content-selling"), expect.objectContaining({ method: "PATCH", body: JSON.stringify({ value: true }) })));
    expect(screen.getAllByText("CONTENT SALES")).toHaveLength(2);
  });

  it("distinguishes customer configuration from a global ceiling", async () => {
    const blocked = customerState({ contentSellingEnabled: true }, { contentSellingEnabled: false });
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("customer-controls-inventory") ? response({ items: [person], total: 1, page: 1, pageSize: 100 }) : response(blocked));
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    fireEvent.click(await screen.findByRole("row", { name: /Alex/ }));
    expect(await screen.findByText(/Global Content Selling is off/)).toBeInTheDocument();
    expect(screen.getByText("CHAT ONLY")).toBeInTheDocument();
  });

  it("deep-links to a selected customer and back to the same Chat conversation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("customer-controls-inventory") ? response({ items: [person], total: 1, page: 1, pageSize: 100 }) : response(customerState()));
    function Location() { return <output data-testid="location">{useLocation().pathname}{useLocation().search}</output>; }
    render(<MemoryRouter initialEntries={[`/business/controls?tab=customers&relationship=${encodeURIComponent(person.personKey)}`]}><BusinessControlsPage/><Location/></MemoryRouter>);
    const link = await screen.findByRole("link", { name: /View Conversation/ });
    fireEvent.click(link);
    expect(screen.getByTestId("location")).toHaveTextContent(`/business/relationships?relationship=${encodeURIComponent(person.personKey)}`);
  });

  it("warns accurately before disabling selling around existing obligations", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("customer-controls-inventory") ? response({ items: [{...person, controls: {...person.controls, sessionSellingEnabled: true}}], total: 1, page: 1, pageSize: 100 }) : response(customerState({ sessionSellingEnabled: true })));
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    fireEvent.click(await screen.findByRole("row", { name: /Alex/ }));
    fireEvent.click((await screen.findByLabelText("SESSION SELLING customer control")).querySelectorAll("button")[0]!);
    expect(screen.getByRole("dialog")).toHaveTextContent("current purchased or active session is preserved");
    expect(screen.getByRole("dialog")).toHaveTextContent("existing presented offer may still settle");
  });

  it("derives every operator effective-mode label", () => {
    expect(effectiveMode(customerState({ avaChatEnabled: false }))).toBe("MANUAL");
    expect(effectiveMode(customerState())).toBe("CHAT ONLY");
    expect(effectiveMode(customerState({ contentSellingEnabled: true }))).toBe("CONTENT SALES");
    expect(effectiveMode(customerState({ sessionSellingEnabled: true }))).toBe("SESSION SALES");
    expect(effectiveMode(customerState({ contentSellingEnabled: true, sessionSellingEnabled: true }))).toBe("ALL SALES");
  });

  it("keeps controls default and exposes identity, intelligence, and shared context preview", async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>{
      const url=String(input);
      if(url.includes("customer-controls-inventory"))return response({items:[person],total:1,page:1,pageSize:100});
      if(url.includes("relationship-context-preview"))return response({relationshipContext:{facts:[],silentFacts:[],exclusions:[]},commerceSummary:{purchaseCount:2}});
      return response(customerState());
    });
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    fireEvent.click(await screen.findByRole("row",{name:/Alex/}));
    expect(screen.getByText("The operational controls above remain authoritative and independent.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"IDENTITY"}));
    expect(screen.getByText("Platform identities")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"CONTEXT PREVIEW"}));
    fireEvent.change(screen.getByLabelText("Sample message"),{target:{value:"How is Bully?"}});
    fireEvent.click(screen.getByRole("button",{name:"Preview Ava Context"}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("customer_id=44"),expect.anything()));
    expect(await screen.findByText(/2 transactions/)).toBeInTheDocument();
  });

  it("renders the authoritative customer snapshot without exposing the structured editor",async()=>{
    const snapshot={identity_summary:{subjectType:"CUSTOMER",customerId:"44",telegramUserId:"1"},mapping_state:"MAPPED_VERIFIED",sources:["TELEGRAM_CONVERSATIONAL_MEMORY","CANONICAL_RELATIONSHIP_FACT","CREATOR_FACT"],excluded_items:[],sections:{PERSONAL:[{item_id:"telegram:1:pet:0",subject_type:"CUSTOMER",subject_id:"44",section:"PERSONAL",label:"Bully",description:"Dog · Customer's pet",value:{name:"Bully"},attributes:{type:"dog"},source_authority:"TELEGRAM_CONVERSATIONAL_MEMORY",source_platform:"TELEGRAM",confidence:.95,usage_policy:"NORMAL_CONTEXT",lifecycle_status:"CURRENT",observed_at:"2026-09-10",last_observed_at:"2026-09-11",correctable:false,native_reference:{store:"telegram_sales_prospects.preference_state"},inferred:false,exclusion_reason:null}],SILENT_CONTEXT:[{item_id:"canonical:s1",subject_type:"CUSTOMER",subject_id:"44",section:"SILENT_CONTEXT",label:"AI image context",description:"Understands",value:"AI image context",attributes:{},source_authority:"CANONICAL_RELATIONSHIP_FACT",source_platform:"CREATOR_OS",confidence:1,usage_policy:"SILENT_CONTEXT",lifecycle_status:"ACTIVE",observed_at:null,last_observed_at:null,correctable:true,native_reference:{factId:"s1"},inferred:false,exclusion_reason:null}],RELEVANT_CREATOR_FACTS:[{item_id:"canonical:c1",subject_type:"CREATOR",subject_id:"2",section:"RELEVANT_CREATOR_FACTS",label:"JoJo",description:"Owns Pet",value:"JoJo",attributes:{type:"dog"},source_authority:"CREATOR_FACT",source_platform:"CREATOR_OS",confidence:1,usage_policy:"NORMAL_CONTEXT",lifecycle_status:"ACTIVE",observed_at:null,last_observed_at:null,correctable:true,native_reference:{factId:"c1"},inferred:false,exclusion_reason:null}]}};
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>{const url=String(input);if(url.includes("customer-controls-inventory"))return response({items:[person],total:1,page:1,pageSize:100});if(url.includes("customer-snapshot"))return response(snapshot);return response(customerState())});
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);fireEvent.click(await screen.findByRole("row",{name:/Alex/}));fireEvent.click(screen.getByRole("button",{name:"INTELLIGENCE"}));
    expect(await screen.findByLabelText("Customer snapshot")).toHaveTextContent("Bully");expect(screen.getByText("Learned from Telegram")).toBeInTheDocument();expect(screen.getByText("Verified Intelligence")).toBeInTheDocument();expect(screen.getByText("Ava / Creator Fact")).toBeInTheDocument();expect(screen.getByText("SILENT")).toBeInTheDocument();expect(screen.getByText(/Used quietly/)).toBeInTheDocument();expect(screen.getByText(/This is about Ava/)).toBeInTheDocument();
    expect(screen.queryByText("Add Intelligence")).not.toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:/Add Something Ava Should Know/}));expect(screen.getByLabelText("Something Ava should know")).toBeInTheDocument();expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("customer_id=44"),expect.anything());
  });

  it("renders a selected unmapped Telegram prospect snapshot",async()=>{
    const prospect={...person,localFanvueUserId:null,rowKind:"TELEGRAM_PROSPECT" as const,displayName:"Telegram Prospect",controlAvailability:"UNAVAILABLE" as const,controls:null,platforms:{fanvue:"NOT_OBSERVED",telegram:"OBSERVED",x:"NOT_OBSERVED"}};
    vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("customer-controls-inventory")?response({items:[prospect],total:1,page:1,pageSize:100}):String(input).includes("customer-snapshot")?response({identity_summary:{subjectType:"TELEGRAM_PROSPECT",telegramUserId:"1"},mapping_state:"TELEGRAM_PROSPECT_NOT_MAPPED",sources:[],excluded_items:[],sections:{}}):response(customerState()));
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);fireEvent.click(await screen.findByRole("row",{name:/Telegram Prospect/}));fireEvent.click(screen.getByRole("button",{name:"INTELLIGENCE"}));expect(await screen.findByText(/TELEGRAM PROSPECT · NOT MAPPED/)).toBeInTheDocument();expect(screen.getByText("No customer intelligence yet.")).toBeInTheDocument();
  });

  it("previews, selectively applies, prevents duplicate submits, marks silent, and refreshes the snapshot",async()=>{
    let snapshotReads=0;let resolveApply!:(value:Response)=>void;const pendingApply=new Promise<Response>(resolve=>{resolveApply=resolve});
    const proposals={mutationPerformed:false,providerCalls:0,parser:"DETERMINISTIC_BOUNDED",proposals:[{proposalId:"pet",label:"Bully",meaning:"Alex's female dog",subjectLabel:"Alex",sourceLabel:"Operator provided",usagePolicy:"NORMAL_CONTEXT",validationState:"READY",warnings:[]},{proposalId:"ai",label:"AI Images",meaning:"Bully sometimes appears in Alex's recurring AI images with Ava",subjectLabel:"Alex",sourceLabel:"Operator provided",usagePolicy:"NORMAL_CONTEXT",validationState:"READY",warnings:[]}]};
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{const url=String(input);if(url.includes("customer-controls-inventory"))return response({items:[person],total:1,page:1,pageSize:100});if(url.includes("customer-snapshot")){snapshotReads++;return response({identity_summary:{},mapping_state:"MAPPED_VERIFIED",sources:[],excluded_items:[],sections:snapshotReads>1?{PREFERENCES:[{item_id:"new",subject_type:"CUSTOMER",subject_id:"44",section:"PREFERENCES",label:"New intelligence",description:"Preference",value:"New intelligence",attributes:{},source_authority:"CANONICAL_RELATIONSHIP_FACT",source_platform:"CREATOR_OS",confidence:1,usage_policy:"NORMAL_CONTEXT",lifecycle_status:"CURRENT",observed_at:null,last_observed_at:null,correctable:true,native_reference:{factId:"new"},inferred:false,exclusion_reason:null}]}:{}})}if(url.endsWith("/preview"))return response(proposals);if(url.endsWith("/apply")){expect(init?.method).toBe("POST");return pendingApply}return response(customerState())});
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);fireEvent.click(await screen.findByRole("row",{name:/Alex/}));fireEvent.click(screen.getByRole("button",{name:"INTELLIGENCE"}));await screen.findByText("No customer intelligence yet.");fireEvent.click(screen.getByRole("button",{name:/Add Something Ava Should Know/}));fireEvent.change(screen.getByLabelText("Something Ava should know"),{target:{value:"Alex's dog is Bully. She's a girl and sometimes appears in AI pictures with Ava."}});fireEvent.click(screen.getByRole("button",{name:"Preview"}));expect(await screen.findByText("I FOUND 2 FACTS")).toBeInTheDocument();fireEvent.click(screen.getByLabelText("Select Bully"));fireEvent.click(screen.getByLabelText("Mark AI Images silent"));const add=screen.getByRole("button",{name:"Add 1 Fact"});fireEvent.click(add);fireEvent.click(add);expect(fetchMock.mock.calls.filter(([url])=>String(url).endsWith("/apply"))).toHaveLength(1);resolveApply(await response({success:true,createdCount:1}));expect(await screen.findByText("New intelligence")).toBeInTheDocument();expect(snapshotReads).toBeGreaterThan(1);
  });

  it("shows already-known and conflict proposals without offering them for creation",async()=>{
    const proposals={mutationPerformed:false,providerCalls:0,parser:"DETERMINISTIC_BOUNDED",proposals:[{proposalId:"known",label:"Bully",meaning:"Alex's female dog",subjectLabel:"Alex",sourceLabel:"Operator provided",usagePolicy:"NORMAL_CONTEXT",validationState:"ALREADY_KNOWN",warnings:["Already known"]},{proposalId:"conflict",label:"Bully",meaning:"Proposed gender: male",subjectLabel:"Alex",sourceLabel:"Operator provided",usagePolicy:"NORMAL_CONTEXT",validationState:"CONFLICT",warnings:["CONFLICT WITH EXISTING INTELLIGENCE"],current:{label:"Bully",attributes:{gender:"female"}}}]};
    vi.spyOn(globalThis,"fetch").mockImplementation(input=>{const url=String(input);if(url.includes("customer-controls-inventory"))return response({items:[person],total:1,page:1,pageSize:100});if(url.includes("customer-snapshot"))return response({identity_summary:{},mapping_state:"MAPPED_VERIFIED",sources:[],excluded_items:[],sections:{}});if(url.endsWith("/preview"))return response(proposals);return response(customerState())});
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);fireEvent.click(await screen.findByRole("row",{name:/Alex/}));fireEvent.click(screen.getByRole("button",{name:"INTELLIGENCE"}));await screen.findByText("No customer intelligence yet.");fireEvent.click(screen.getByRole("button",{name:/Add Something Ava Should Know/}));fireEvent.change(screen.getByLabelText("Something Ava should know"),{target:{value:"Bully is male."}});fireEvent.click(screen.getByRole("button",{name:"Preview"}));expect(await screen.findByText("ALREADY KNOWN")).toBeInTheDocument();expect(screen.getByText("CONFLICT")).toBeInTheDocument();expect(screen.getByText(/Gender female/)).toBeInTheDocument();expect(screen.getByRole("button",{name:"Add 0 Facts"})).toBeDisabled();fireEvent.click(screen.getByRole("button",{name:"Edit"}));expect(screen.getByLabelText("Something Ava should know")).toHaveValue("Bully is male.");fireEvent.click(screen.getByRole("button",{name:"Cancel"}));expect(screen.queryByLabelText("Add customer intelligence")).not.toBeInTheDocument();
  });

  it("shows a Fanvue-only canonical buyer without fake Telegram controls or navigation", async()=>{
    const wally:CustomerInventoryItem={...person,rowKey:"customer:2:2:7245",personKey:"customer:2:2:7245",rowKind:"CANONICAL_CUSTOMER",relationshipKey:null,hasConversation:false,telegramUserId:null,controlAvailability:"UNAVAILABLE",controls:null,displayName:"papi80",username:"papi80",metadataComplete:false,providerEvidenceAvailable:true,identityStatus:"NOT_OBSERVED",platforms:{fanvue:"CANONICAL",telegram:"NOT_OBSERVED",x:"NOT_OBSERVED"},commerce:{lifetimeGrossMinor:11996,lifetimeNetMinor:9596,purchaseCount:5,firstPurchaseAt:"2026-08-07",lastPurchaseAt:"2026-08-29",lastSyncedAt:"2026-08-29",ownedAssetCount:0},lifetimeVerifiedRevenueMinor:11996,qualifyingPurchaseCount:5};
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(()=>response({items:[wally],total:1,page:1,pageSize:100}));
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    fireEvent.click(await screen.findByRole("row",{name:/papi80/}));
    expect(screen.getByText(/Not available yet/)).toBeInTheDocument();
    expect(screen.queryByLabelText("AVA AUTO control")).not.toBeInTheDocument();
    expect(screen.queryByRole("link",{name:/View Conversation/})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"COMMERCE"}));
    const summary=screen.getByLabelText("Customer commerce summary");
    expect(summary.querySelectorAll(".commerce-metric")).toHaveLength(3);expect(summary.querySelector(".commerce-metrics")).toBeInTheDocument();
    expect(screen.getByText("$119.96")).toBeInTheDocument();expect(screen.getByText("$95.96")).toBeInTheDocument();expect(screen.getByText("5")).toBeInTheDocument();
    const history=screen.getByRole("heading",{name:"PURCHASE HISTORY"}).closest("section");expect(history).toHaveTextContent("First PurchaseAug 7, 2026");expect(history).toHaveTextContent("Latest PurchaseAug 29, 2026");expect(history).toHaveTextContent("Last SyncAug 29, 2026");expect(history).toHaveTextContent("Provider data may be stale");
    const attribution=screen.getByRole("heading",{name:"CONTENT ATTRIBUTION"}).closest("section");expect(attribution).toHaveTextContent("Attributed Assets0");expect(attribution).toHaveTextContent("UNATTRIBUTED / UNRESOLVED");
    expect(summary).toHaveTextContent("Verified purchases are financial evidence");
    fireEvent.click(screen.getByRole("button",{name:"CONTEXT PREVIEW"}));
    expect(screen.getByText(/NO VERIFIED TELEGRAM IDENTITY/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("restores canonical customer and detail section from URL",async()=>{
    const wally:CustomerInventoryItem={...person,rowKey:"customer:2:2:7245",personKey:"customer:2:2:7245",rowKind:"CANONICAL_CUSTOMER",relationshipKey:null,hasConversation:false,telegramUserId:null,controlAvailability:"UNAVAILABLE",controls:null,displayName:"Wally",commerce:{...person.commerce,lifetimeGrossMinor:11996,lifetimeNetMinor:9596,purchaseCount:5}};
    vi.spyOn(globalThis,"fetch").mockImplementation(()=>response({items:[wally],total:1,page:1,pageSize:100}));
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers&relationship=customer%3A2%3A2%3A7245&section=commerce"]}><BusinessControlsPage/></MemoryRouter>);
    expect(await screen.findByText("$119.96")).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"COMMERCE"})).toHaveAttribute("aria-pressed","true");
  });

  it("previews metadata and renders human-readable selective context",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(input=>{const url=String(input);if(url.includes("customer-controls-inventory"))return response({items:[{...person,metadataComplete:false,providerEvidenceAvailable:true}],total:1,page:1,pageSize:100});if(url.includes("metadata-enrichment-preview"))return response({customer:{username:null,displayName:null,source:null},changes:{username:"papi80",display_name:"Wally",source:"provider_verified_earnings"},conflicts:{},evidence:{type:"PROVIDER_VERIFIED_EARNINGS"},canApply:true});if(url.includes("relationship-context-preview"))return response({commerceSummary:{purchaseCount:5,lifetimeGrossMinor:11996,lifetimeNetMinor:9596},relationshipContext:{facts:[{factId:"1",subject:{type:"CUSTOMER"},relation:"owns_pet",object:{value:"Bully"}}],silentFacts:[],exclusions:[{factId:"2",reason:"NOT_RELEVANT"}]}});return response(customerState())});
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);fireEvent.click(await screen.findByRole("row",{name:/Alex/}));fireEvent.click(screen.getByRole("button",{name:"IDENTITY"}));fireEvent.click(screen.getByRole("button",{name:"Preview Enrichment"}));expect(await screen.findByText(/provider_verified_earnings/)).toBeInTheDocument();expect(fetchMock.mock.calls.filter(([url])=>String(url).includes("metadata-enrichment")).length).toBe(1);
    fireEvent.click(screen.getByRole("button",{name:"CONTEXT PREVIEW"}));fireEvent.change(screen.getByLabelText("Sample message"),{target:{value:"Bully appeared"}});fireEvent.click(screen.getByRole("button",{name:"Preview Ava Context"}));expect(await screen.findByText(/Bully · Owns Pet/)).toBeInTheDocument();expect(screen.getByText(/Not Relevant/)).toBeInTheDocument();
  });

  it("applies enrichment once, consumes the authoritative customer, refreshes inventory, and resets preview",async()=>{
    const incomplete={...person,displayName:"papi80",username:null,metadataComplete:false,providerEvidenceAvailable:true};
    const complete={...incomplete,displayName:"Wally",username:"papi80",metadataComplete:true};let inventoryReads=0;
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{const url=String(input);if(url.includes("customer-controls-inventory")){inventoryReads++;return response({items:[inventoryReads===1?incomplete:complete],total:1,page:1,pageSize:100})}if(url.includes("metadata-enrichment-preview"))return response({customer:{username:null,displayName:null,source:null},changes:{username:"papi80",display_name:"Wally",source:"provider_verified_earnings"},conflicts:{},evidence:{type:"PROVIDER_VERIFIED_EARNINGS"},canApply:true});if(url.includes("/metadata-enrichment")){expect(init?.method).toBe("POST");return response({status:"APPLIED",idempotent:false,customer:{id:44,username:"papi80",display_name:"Wally",source:"provider_verified_earnings"}})}return response(customerState())});
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);fireEvent.click(await screen.findByRole("row",{name:/papi80/}));fireEvent.click(screen.getByRole("button",{name:"IDENTITY"}));fireEvent.click(screen.getByRole("button",{name:"Preview Enrichment"}));const apply=await screen.findByRole("button",{name:"Apply Enrichment"});fireEvent.click(apply);fireEvent.click(apply);
    expect(await screen.findByText(/Authoritative result: APPLIED/)).toBeInTheDocument();await waitFor(()=>expect(screen.getByRole("complementary",{name:"Customer Controls"})).toHaveTextContent("Wally"));expect(screen.queryByText("PROPOSED")).not.toBeInTheDocument();expect(screen.queryByText("Metadata incomplete")).not.toBeInTheDocument();expect(inventoryReads).toBeGreaterThan(1);expect(fetchMock.mock.calls.filter(([url,init])=>String(url).endsWith("/metadata-enrichment")&&init?.method==="POST")).toHaveLength(1);
  });

  it("keeps the preview and shows a visible error when enrichment fails",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>{const url=String(input);if(url.includes("customer-controls-inventory"))return response({items:[{...person,metadataComplete:false,providerEvidenceAvailable:true}],total:1,page:1,pageSize:100});if(url.includes("metadata-enrichment-preview"))return response({customer:{username:null},changes:{username:"papi80"},conflicts:{},evidence:{type:"PROVIDER_VERIFIED_EARNINGS"},canApply:true});if(url.endsWith("/metadata-enrichment"))return response({detail:"Enrichment transaction failed."},500);return response(customerState())});
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);fireEvent.click(await screen.findByRole("row",{name:/Alex/}));fireEvent.click(screen.getByRole("button",{name:"IDENTITY"}));fireEvent.click(screen.getByRole("button",{name:"Preview Enrichment"}));fireEvent.click(await screen.findByRole("button",{name:"Apply Enrichment"}));expect(await screen.findByRole("alert")).toHaveTextContent("Enrichment transaction failed.");expect(screen.getByText("PROPOSED")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Apply Enrichment"})).toBeEnabled();
  });
  it("refreshes a persisted broadcast observation without granting private-chat capabilities",async()=>{
    let inventoryReads=0;
    const wally={...person,displayName:"Wally",username:"papi80",platforms:{...person.platforms,telegram:"NOT_OBSERVED"},telegramObservation:{sources:[],sourceChannelId:null,privateChatEstablished:false,participantStatus:null},telegramUserId:null,relationshipKey:null,hasConversation:false,controlAvailability:"UNAVAILABLE" as const,controls:null};
    const observed={telegramUserId:"123456",telegramUserIdMasked:"***3456",username:"wm",displayName:"Wally McClung",status:"UNMAPPED",source:"BROADCAST_SUBSCRIBER",observationSources:["BROADCAST_MEMBER"],privateChatEstablished:false,participantStatus:"ChannelParticipant"};
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input)=>{const url=String(input);if(url.includes("customer-controls-inventory")){inventoryReads++;return response({items:[wally],total:1,page:1,pageSize:100})}if(url.includes("broadcast-members"))return response({channelId:-1001,mutationPerformed:false,items:[{telegramUserId:123456,username:"wm",displayName:"Wally McClung",participantStatus:"ChannelParticipant",channelId:-1001}]});if(url.includes("broadcast-observations"))return response({telegram_user_id:123456,observation_sources:["BROADCAST_MEMBER"],private_chat_id:null});if(url.includes("telegram-identity-readiness"))return response({items:[observed],fanvueCandidates:[],counts:{unmapped:1}});if(url.includes("/x/observations"))return response([]);return response(customerState())});
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    fireEvent.click(await screen.findByRole("row",{name:/Wally/}));fireEvent.click(screen.getByRole("button",{name:"IDENTITY"}));fireEvent.change(screen.getByLabelText("Telegram subscriber search"),{target:{value:"Wally McClung"}});fireEvent.click(screen.getByRole("button",{name:"Find Telegram Subscriber"}));fireEvent.click(await screen.findByRole("button",{name:/Select Wally McClung/}));
    const persist=screen.getByRole("button",{name:"Persist Observation"});fireEvent.click(persist);fireEvent.click(persist);
    expect(await screen.findByText(/BROADCAST_OBSERVATION_PERSISTED/)).toBeInTheDocument();
    expect(screen.getByText("OBSERVED — BROADCAST")).toBeInTheDocument();expect(screen.getAllByText("Private chat: Not established").length).toBeGreaterThan(0);expect(screen.getAllByText("Mapping: Unverified").length).toBeGreaterThan(0);
    expect(screen.getByRole("option",{name:/Wally McClung.*@wm.*Broadcast Member/})).toBeInTheDocument();expect(screen.queryByText("Select private-chat observation")).not.toBeInTheDocument();
    expect(screen.queryByRole("link",{name:/View Conversation/})).not.toBeInTheDocument();expect(screen.queryByLabelText("AVA AUTO control")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url])=>String(url).includes("broadcast-observations"))).toHaveLength(1);expect(fetchMock.mock.calls.some(([url])=>String(url).includes("/verify"))).toBe(false);expect(inventoryReads).toBeGreaterThan(1);
  });

  it("shows a visible error and allows retry when broadcast persistence fails",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>{const url=String(input);if(url.includes("customer-controls-inventory"))return response({items:[person],total:1,page:1,pageSize:100});if(url.includes("broadcast-members"))return response({items:[{telegramUserId:123456,displayName:"Wally McClung",channelId:-1001}]});if(url.includes("broadcast-observations"))return response({detail:"Observation transaction failed."},500);return response([])});
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);fireEvent.click(await screen.findByRole("row",{name:/Alex/}));fireEvent.click(screen.getByRole("button",{name:"IDENTITY"}));fireEvent.change(screen.getByLabelText("Telegram subscriber search"),{target:{value:"Wally"}});fireEvent.click(screen.getByRole("button",{name:"Find Telegram Subscriber"}));fireEvent.click(await screen.findByRole("button",{name:/Select Wally/}));fireEvent.click(screen.getByRole("button",{name:"Persist Observation"}));expect(await screen.findByRole("alert")).toHaveTextContent("Observation transaction failed.");expect(screen.getByRole("button",{name:"Persist Observation"})).toBeEnabled();
  });
});
