import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiTrainingWorkspacePage } from "./AiTrainingWorkspacePage";

const person = { personKey: "telegram:7:8:1", telegramUserId: 1, displayName: "Alex", username: "alex", identityStatus: "UNMAPPED", buyerStatus: null, lifetimeVerifiedRevenueMinor: null, qualifyingPurchaseCount: null, latestActivityAt: "2026-09-06T14:00:00Z", latestMessagePreview: "hello", activePurchaseIntent: false, activeSalesSession: false };
const response = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
const renderPage = (entry = "/training/ai-training") => render(<MemoryRouter initialEntries={[entry]}><Routes><Route path="/training/ai-training" element={<AiTrainingWorkspacePage />} /><Route path="/agents/ai-training" element={<p>Advanced rules</p>} /></Routes></MemoryRouter>);
afterEach(() => vi.restoreAllMocks());

describe("AI Training workspace", () => {
  it("defaults to Global and reads the canonical Ava Rules authority", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ items: [{ instructionId: "one", instructionType: "CONVERSATION_RULE", originalOperatorText: "Be concise", normalizedInstruction: "Be concise", status: "ENABLED", priority: 100, classificationReason: "Eligible", version: 2, createdAt: "2026-08-24T00:00:00Z", updatedAt: "2026-08-25T00:00:00Z", enabledAt: "2026-08-24T00:00:00Z", disabledAt: null, archivedAt: null, policyKey: null, enforcementMode: "PROMPT" }] }));
    renderPage();
    expect(await screen.findByRole("heading", { name: "AI Training" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "GLOBAL" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("Be concise")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ New Training" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Advanced Rule Details" })).toHaveAttribute("href", "/agents/ai-training");
    expect(fetchMock.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("shows customer facts separately from deliberately inactive training", async () => {
    // Customer composition remains independent from the Global rule list.
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("/customer-treatment/") ? response({ eligible:false, configuration:{sales_pressure:"NORMAL",free_engagement:"NORMAL",response_length:"NORMAL"},usingAvaDefaults:true,runtimeEffect:"NONE_PHASE_2A",item:null }) : String(input).includes("/ai-training-controls/customers/") ? response({ eligible: false, eligibilityReason: "A verified customer identity is required before training can be activated.", items: [] }) : String(input).includes("/intelligence") ? response({ person, mappingStatus: "UNMAPPED", partial: true, relationshipIntelligence: { location: "Austin", timezone: "America/Chicago", interests: ["hiking"], pets: ["Milo"], music: [], preferences: [] } }) : response({ items: [{ ...person, isBuyer: false }], nextCursor: null, hasMore: false, sort: "LATEST_ACTIVITY" }));
    renderPage("/training/ai-training?tab=customers&customer=telegram%3A7%3A8%3A1");
    expect(await screen.findByText("Austin")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Known Facts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How Ava Should Behave" })).toBeInTheDocument();
    expect((await screen.findAllByText(/verified customer identity is required/i)).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByRole("button", { name: /save|activate/i })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("renders all Global status collections in the full-width vertical list", async () => {
    const rule = (instructionId: string, normalizedInstruction: string, status: string, instructionType = "CONVERSATION_RULE") => ({ instructionId, instructionType, originalOperatorText: normalizedInstruction, normalizedInstruction, status, priority: 100, classificationReason: "Canonical classification", version: 2, createdAt: "2026-08-24T00:00:00Z", updatedAt: "2026-08-25T00:00:00Z", enabledAt: status === "ENABLED" ? "2026-08-24T00:00:00Z" : null, disabledAt: null, archivedAt: null, policyKey: null, enforcementMode: instructionType === "CONVERSATION_RULE" ? "PROMPT" : "BACKEND" });
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ items: [
      rule("one", "Ava only offers solo content and does not claim unavailable partner content.", "ENABLED"),
      rule("two", "Adaptive Sales Readiness", "DRAFT", "SALES_RULE"),
      rule("three", "Underage Customer Hard Stop", "DISABLED", "SAFETY_HARD_STOP"),
      rule("four", "Intelligent Free Engagement Teasers", "REQUIRES_IMPLEMENTATION", "ENGAGEMENT_RULE"),
    ] }));
    const { container } = renderPage();
    await screen.findByText("Ava only offers solo content and does not claim unavailable partner content.");
    expect(container.querySelector(".training-controls-page--vertical")).toBeInTheDocument();
    for (const text of ["Adaptive Sales Readiness", "Underage Customer Hard Stop", "Intelligent Free Engagement Teasers"])
      expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.getAllByText("Priority 100")).toHaveLength(4);
    expect(screen.getAllByText("v2")).toHaveLength(4);
    expect(screen.getAllByText(/Updated/)).toHaveLength(4);
    expect(screen.getAllByLabelText("Edit instruction")).toHaveLength(4);
    expect(screen.getAllByLabelText("Archive instruction")).toHaveLength(4);
  });

  it("searches existing relationship identities without cross-customer leakage", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => response({ items: String(input).includes("search=Blair") ? [{ ...person, personKey: "telegram:7:8:2", displayName: "Blair" }] : [person], nextCursor: null, hasMore: false, sort: "LATEST_ACTIVITY" }));
    renderPage("/training/ai-training?tab=customers");
    fireEvent.change(await screen.findByLabelText("Search customers"), { target: { value: "Blair" } });
    expect(await screen.findByRole("button", { name: /Blair/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Alex/ })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("search=Blair"), expect.anything());
  });

  it("reviews and explicitly applies structured customer treatment without an eager save", async () => {
    const mapped={...person,identityStatus:"MAPPED_VERIFIED",isBuyer:true};
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{
      const url=String(input);
      if(url.includes("/intelligence"))return response({person:mapped,mappingStatus:"VERIFIED",partial:false,relationshipIntelligence:{location:null,timezone:null,interests:[],pets:[],music:[],preferences:[]}});
      if(url.includes("/customer-treatment/preview"))return response({configuration:{sales_pressure:"REDUCED",free_engagement:"NORMAL",response_length:"SHORTER"},usingAvaDefaults:false,runtimeEffect:"BOUNDED_PHASE_2B",protectedAuthorities:["SAFETY"],treatmentType:"CUSTOMER_TREATMENT_POLICY"});
      if(url.includes("/customer-treatment/")&&init?.method==="PUT")return response({eligible:true,configuration:{sales_pressure:"REDUCED",free_engagement:"NORMAL",response_length:"SHORTER"},usingAvaDefaults:false,runtimeEffect:"BOUNDED_PHASE_2B",item:{instructionId:"t1",status:"ENABLED",version:1}});
      if(url.includes("/customer-treatment/"))return response({eligible:true,configuration:{sales_pressure:"NORMAL",free_engagement:"NORMAL",response_length:"NORMAL"},usingAvaDefaults:true,runtimeEffect:"BOUNDED_PHASE_2B",item:null});
      if(url.includes("/ai-training-controls/customers/"))return response({eligible:true,eligibilityReason:null,items:[]});
      return response({items:[mapped],nextCursor:null,hasMore:false,sort:"LATEST_ACTIVITY"});
    });
    renderPage("/training/ai-training?tab=customers&customer=telegram%3A7%3A8%3A1");
    expect(await screen.findByText("Using Ava defaults")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Advanced Treatment Controls"));
    fireEvent.click(screen.getByRole("button",{name:"REDUCED"}));
    fireEvent.click(screen.getByRole("button",{name:"SHORTER"}));
    expect(fetchMock.mock.calls.some(([,init])=>init?.method==="PUT")).toBe(false);
    fireEvent.click(screen.getByRole("button",{name:"Review Changes"}));
    expect(await screen.findByRole("button",{name:"Apply Treatment"})).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"Apply Treatment"}));
    await vi.waitFor(()=>expect(fetchMock.mock.calls.some(([,init])=>init?.method==="PUT")).toBe(true));
  });

  it("keeps Customers management-only while retaining edits for existing training",async()=>{
    const mapped={...person,identityStatus:"MAPPED_VERIFIED",isBuyer:true};
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input)=>{const url=String(input);
      if(url.includes("/intelligence"))return response({person:mapped,mappingStatus:"VERIFIED",partial:false,relationshipIntelligence:{interests:[],pets:[],music:[],preferences:[]}});
      if(url.endsWith("/analyze"))return response({operatorText:"Be warmer and keep replies shorter",supported:true,classification:"CUSTOMER_TRAINING_PLAN",explanation:"Review",conversationGuidance:["Be warmer with this customer."],treatment:{sales_pressure:"NORMAL",free_engagement:"NORMAL",response_length:"SHORTER"},protectedAuthorities:["SAFETY"]});
      if(url.endsWith("/apply-plan"))return response({guidance:[],treatment:{instructionId:"t1"},configuration:{sales_pressure:"NORMAL",free_engagement:"NORMAL",response_length:"SHORTER"},usingAvaDefaults:false});
      if(url.includes("/customer-treatment/"))return response({eligible:true,configuration:{sales_pressure:"NORMAL",free_engagement:"NORMAL",response_length:"NORMAL"},usingAvaDefaults:true,runtimeEffect:"BOUNDED_PHASE_2B",item:null});
      if(url.includes("/ai-training-controls/customers/"))return response({eligible:true,eligibilityReason:null,items:[{instructionId:"g1",instructionType:"CONVERSATION_RULE",originalOperatorText:"Be warm",normalizedInstruction:"Be warm",status:"ENABLED",priority:100,version:1,updatedAt:"2026-09-10T00:00:00Z"}]});
      return response({items:[mapped],nextCursor:null,hasMore:false,sort:"LATEST_ACTIVITY"});});
    renderPage("/training/ai-training?tab=customers&customer=telegram%3A7%3A8%3A1");
    expect(screen.queryByLabelText("What should Ava do differently with this customer?")).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Analyze Training"})).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button",{name:"Edit"}));
    const box=screen.getByLabelText("Edit existing customer training");
    fireEvent.change(box,{target:{value:"Be warmer and keep replies shorter"}});
    fireEvent.click(screen.getByRole("button",{name:"Analyze Changes"}));
    expect(await screen.findByText("Be warmer with this customer.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([,init])=>init?.method==="POST"&&String(init.body).includes("apply"))).toBe(false);
    fireEvent.click(screen.getByRole("button",{name:"Apply Training"}));
    await vi.waitFor(()=>expect(fetchMock.mock.calls.some(([,init])=>init?.method==="PUT")).toBe(true));
  });

  it("loads global revisions and fabricates no customer history", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ baselineAt:"2026-09-10T00:00:00Z",items: [{ instructionId: "one", scope: "GLOBAL", instructionType: "CONVERSATION_RULE", originalOperatorText: "Be concise", normalizedInstruction: "Be concise", status: "ENABLED", priority: 100, classificationReason: "Eligible", version: 2, createdAt: "2026-08-24T00:00:00Z", updatedAt: "2026-08-25T00:00:00Z", enabledAt: "2026-08-24T00:00:00Z", disabledAt: null, archivedAt: null, policyKey: null, enforcementMode: "PROMPT",implementationStatus:{implemented:true,label:"IMPLEMENTED · ACTIVE"} }] }));
    renderPage("/training/ai-training?tab=history");
    expect(await screen.findByText(/IMPLEMENTED · ACTIVE/)).toBeInTheDocument();
    expect(screen.getByText(/v2/)).toBeInTheDocument();
    expect(screen.getAllByText("GLOBAL").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: "CUSTOMER" })).toBeInTheDocument();
  });

  it("renders one current card per canonical instruction ID without text-based deduplication",async()=>{
    const rule=(instructionId:string,scope:"GLOBAL"|"CUSTOMER")=>({instructionId,scope,customerFanvueUserId:scope==="CUSTOMER"?Number(instructionId):null,instructionType:"CONVERSATION_RULE",originalOperatorText:"Keep replies shorter",normalizedInstruction:"Keep replies shorter",status:"ENABLED",priority:100,classificationReason:"Eligible",version:5,createdAt:"2026-09-11T00:00:00Z",updatedAt:"2026-09-12T00:00:00Z",enabledAt:"2026-09-11T00:00:00Z",disabledAt:null,archivedAt:null,policyKey:null,enforcementMode:"PROMPT",implementationStatus:{implemented:true,label:"IMPLEMENTED · ACTIVE"}});
    vi.spyOn(globalThis,"fetch").mockImplementation(()=>response({baselineAt:"2026-09-10T00:00:00Z",items:[rule("11","CUSTOMER"),rule("22","CUSTOMER")]}));
    const {container}=renderPage("/training/ai-training?tab=history");
    await screen.findAllByText("Keep replies shorter");
    expect(container.querySelectorAll(".training-history-list article")).toHaveLength(2);
    expect(screen.getByText("Customer #11")).toBeInTheDocument();
    expect(screen.getByText("Customer #22")).toBeInTheDocument();
  });

  it("quick-adds a Queue TODO without applying runtime training",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{
      const url=String(input);if(url.includes("/relationships"))return response({items:[],nextCursor:null,hasMore:false});
      if(url.endsWith("/queue")&&init?.method==="POST")return response({workItemId:"q1",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Ava is too wordy",status:"TODO",classification:null,classificationRationale:null,analysis:{},linkedInstructionId:null,linkedFutureTaskId:null,createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null});
      return response({items:[]});
    });
    renderPage("/training/ai-training?tab=queue");
    const scope = await screen.findByRole("combobox", { name: "Scope" });
    expect(scope).toHaveValue("GLOBAL");
    expect(screen.getByRole("option", { name: "GLOBAL" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "CUSTOMER" })).toBeInTheDocument();
    fireEvent.change(scope, { target: { value: "CUSTOMER" } });
    expect(screen.getByRole("combobox", { name: "Queue customer" })).toBeInTheDocument();
    fireEvent.change(scope, { target: { value: "GLOBAL" } });
    fireEvent.change(await screen.findByLabelText("What should Ava learn or do differently?"),{target:{value:"Ava is too wordy"}});
    fireEvent.click(screen.getByRole("button",{name:"+ New Training"}));
    await vi.waitFor(()=>expect(fetchMock.mock.calls.some(([url,init])=>String(url).endsWith("/queue")&&init?.method==="POST")).toBe(true));
    expect(fetchMock.mock.calls.some(([,init])=>String(init?.body||"").includes("activate"))).toBe(false);
  });

  it("opens a Chat deep-link pre-scoped to the canonical customer without creating a Queue item",async()=>{
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")
      ? response({items:[person],nextCursor:null,hasMore:false})
      : response({items:[]}));
    renderPage("/training/ai-training?tab=queue&scope=customer&customer=telegram%3A7%3A8%3A1");
    expect(await screen.findByRole("combobox",{name:"Scope"})).toHaveValue("CUSTOMER");
    expect(await screen.findByRole("combobox",{name:"Queue customer"})).toHaveValue(person.personKey);
    expect(screen.getByLabelText("What should Ava learn or do differently?")).toHaveValue("");
    expect(fetchMock.mock.calls.every(([,init])=>!init?.method||init.method==="GET")).toBe(true);
  });

  it("labels the READY action Launch Training and keeps it explicitly operator-triggered",async()=>{
    const ready={workItemId:"q1",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Be concise",status:"READY_TO_APPLY",classification:"GLOBAL_PROMPT_GUIDANCE",classificationRationale:"Supported",analysis:{},linkedInstructionId:null,linkedFutureTaskId:null,createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null};
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):init?.method==="POST"?response({...ready,status:"IMPLEMENTED",linkedInstructionId:"g1"}):response({items:[ready]}));
    renderPage("/training/ai-training?tab=queue");
    const launch=await screen.findByRole("button",{name:"Launch Training"});
    expect(fetchMock.mock.calls.every(([,init])=>!init?.method||init.method==="GET")).toBe(true);
    fireEvent.click(launch);
    await vi.waitFor(()=>expect(fetchMock.mock.calls.some(([url,init])=>init?.method==="POST"&&String(url).endsWith("/queue/q1/apply"))).toBe(true));
  });

  it("routes implemented customer training by immutable canonical key despite mutable display identity",async()=>{
    const implemented={workItemId:"q2",scope:"CUSTOMER",customerFanvueUserId:1,originalRequestText:"Be warmer",status:"IMPLEMENTED",classification:"CUSTOMER_TRAINING",classificationRationale:"Canonical training applied",analysis:{customerProjectionKey:person.personKey,implementation:{implemented:true,label:"IMPLEMENTED · ACTIVE"}},linkedInstructionId:"g2",linkedFutureTaskId:null,createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>{const url=String(input);const renamed={...person,displayName:"Alex Renamed",username:"new_name",identityStatus:"MAPPED_VERIFIED"};
      if(url.includes("/intelligence"))return response({person:renamed,mappingStatus:"VERIFIED",partial:false,relationshipIntelligence:{interests:[],pets:[],music:[],preferences:[]}});
      if(url.includes("/customer-treatment/"))return response({eligible:true,configuration:{sales_pressure:"NORMAL",free_engagement:"NORMAL",response_length:"NORMAL"},usingAvaDefaults:true,runtimeEffect:"BOUNDED_PHASE_2B",item:null});
      if(url.includes("/ai-training-controls/customers/"))return response({eligible:true,eligibilityReason:null,items:[]});
      if(url.includes("/relationships"))return response({items:[renamed],nextCursor:null,hasMore:false});
      return response({items:[implemented]});});
    renderPage("/training/ai-training?tab=queue");
    fireEvent.click(await screen.findByRole("button",{name:"Implemented"}));
    expect(await screen.findByText("Customer: Alex Renamed")).toBeInTheDocument();
    const view=screen.getByRole("link",{name:"View Training"});
    expect(view).toHaveAttribute("href","/training/ai-training?tab=customers&customer=telegram%3A7%3A8%3A1");
    fireEvent.click(view);
    expect(await screen.findByRole("heading",{name:"Alex Renamed"})).toBeInTheDocument();
  });

  it("requires explicit prepare, approval, and verification for code-backed work",async()=>{
    const required={workItemId:"q-code",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Check actual inventory",status:"REQUIRES_IMPLEMENTATION",classification:"DYNAMIC_AUTHORITY_REQUIRED",classificationRationale:"Needs code",analysis:{},linkedInstructionId:null,linkedFutureTaskId:null,createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null};
    const brief={version:1,request:required.originalRequestText,scope:"GLOBAL",whyImplementationIsRequired:"Needs code",desiredBehavior:required.originalRequestText,protectedAuthorities:["Inventory truth"],acceptanceCriteria:["Check inventory"],regressionBoundaries:["Preserve safety"],proposedVerification:["Focused tests"],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    let current:any=required;
    const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation((input)=>{const url=String(input);if(url.includes("/relationships"))return response({items:[],nextCursor:null,hasMore:false});if(url.endsWith("/implementation/prepare")){current={...required,status:"READY_FOR_IMPLEMENTATION",analysis:{implementationBrief:brief},linkedFutureTaskId:"task-1"};return response(current)}if(url.endsWith("/implementation/start")){current={...current,status:"IMPLEMENTING",analysis:{...current.analysis,implementationExecutionId:"exec-1"}};return response(current)}if(url.endsWith("/implementation/verify")){current={...current,status:"IMPLEMENTED"};return response(current)}return response({items:[current]})});
    renderPage("/training/ai-training?tab=queue");
    expect(await screen.findByRole("button",{name:"Prepare Implementation"})).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Launch Training"})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"Prepare Implementation"}));
    expect(await screen.findByRole("button",{name:"Approve & Start Implementation"})).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url])=>String(url).endsWith("/implementation/start"))).toHaveLength(0);
    fireEvent.click(screen.getByRole("button",{name:"Approve & Start Implementation"}));
    expect(await screen.findByRole("button",{name:"View Job"})).toBeInTheDocument();
  });

  it("renders complete bounded verification evidence for a successful result",async()=>{
    const brief={version:1,request:"Check inventory",scope:"GLOBAL",whyImplementationIsRequired:"Dynamic truth",desiredBehavior:"Consult inventory",protectedAuthorities:["Inventory truth"],acceptanceCriteria:["Never fabricate"],regressionBoundaries:["Preserve pricing"],proposedVerification:["Focused tests"],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    const item:any={workItemId:"result-1",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Check inventory",status:"NEEDS_VERIFICATION",classification:"DYNAMIC_AUTHORITY_REQUIRED",classificationRationale:"Needs code",analysis:{implementationBrief:brief},linkedInstructionId:null,linkedFutureTaskId:"task-1",createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null,implementation:{brief,execution:{execution_id:"exec-1",task_id:"task-1",status:"COMPLETED",started_at:"2026-09-10T00:00:00Z",completed_at:"2026-09-10T00:10:00Z",failure_reason:null,review_status:"PENDING",final_report:{summary:"Implemented inventory-aware content availability.",files_changed:["app/services/example.py","tests/test_example.py"],tests:[{name:"Backend tests",status:"PASS",count:"12 passed"},{name:"Frontend tests",status:"PASS",count:"4 passed"}],typecheck:"PASS",build:"PASS",warnings:["Existing bundle-size advisory"],migration_required:"YES",migration_applied:"NO",schema_certification:"NOT RUN"}}}};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):String(input).endsWith("/implementation")?response(item):response({items:[item]}));
    renderPage("/training/ai-training?tab=queue");fireEvent.click(await screen.findByRole("button",{name:"Review Result"}));
    expect(await screen.findByText("Implementation completed. Verification required.")).toBeInTheDocument();
    for(const text of ["Implemented inventory-aware content availability.","app/services/example.py","tests/test_example.py","Backend tests — PASS — 12 passed","Frontend tests — PASS — 4 passed","Existing bundle-size advisory","Migration required:","YES","Migration applied:","NO","Schema certification:","NOT RUN"])expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.getByRole("link",{name:"View Job"})).toHaveAttribute("href","/agents/developer");
    expect(screen.getByRole("button",{name:"Verify Implementation"})).toBeInTheDocument();
    expect(screen.queryByRole("region",{name:"Implementation failure"})).not.toBeInTheDocument();
  });

  it("shows unavailable fields honestly and keeps clean results compact",async()=>{
    const brief:any={version:1,request:"Clean task",scope:"GLOBAL",whyImplementationIsRequired:"Code",desiredBehavior:"Do it",protectedAuthorities:[],acceptanceCriteria:[],regressionBoundaries:[],proposedVerification:[],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    const item:any={workItemId:"result-clean",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Clean task",status:"NEEDS_VERIFICATION",classification:"CODE",classificationRationale:"Code",analysis:{implementationBrief:brief},linkedInstructionId:null,linkedFutureTaskId:"task",createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null,implementation:{brief,execution:{execution_id:"exec",task_id:"task",status:"COMPLETED",completed_at:null,final_report:{summary:"Done",filesModified:["app/clean.py"],tests:["All focused tests passed"],validation:{build:"PASS",typecheck:"PASS"},remainingWarnings:[]}}}};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):String(input).endsWith("/implementation")?response(item):response({items:[item]}));
    renderPage("/training/ai-training?tab=queue");fireEvent.click(await screen.findByRole("button",{name:"Review Result"}));
    expect(await screen.findByText("app/clean.py")).toBeInTheDocument();expect(screen.queryByRole("heading",{name:"Warnings"})).not.toBeInTheDocument();expect(screen.queryByRole("heading",{name:"Migration"})).not.toBeInTheDocument();
  });

  it("surfaces failed checks and unapplied migration without hiding operator acceptance",async()=>{
    const brief:any={version:1,request:"Risky task",scope:"GLOBAL",whyImplementationIsRequired:"Code",desiredBehavior:"Do it",protectedAuthorities:[],acceptanceCriteria:[],regressionBoundaries:[],proposedVerification:[],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    const item:any={workItemId:"result-fail",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Risky task",status:"NEEDS_VERIFICATION",classification:"CODE",classificationRationale:"Code",analysis:{implementationBrief:brief},linkedInstructionId:null,linkedFutureTaskId:"task",createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null,implementation:{brief,execution:{execution_id:"exec",task_id:"task",status:"COMPLETED",completed_at:null,final_report:{summary:"Incomplete",filesModified:["app/risky.py"],tests:[{name:"Backend tests",status:"FAIL",count:"1 failed"}],build:"FAIL",migration_required:"YES",migration_applied:"NO",schema_certification:"FAIL"}}}};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):String(input).endsWith("/implementation")?response(item):response({items:[item]}));
    renderPage("/training/ai-training?tab=queue");fireEvent.click(await screen.findByRole("button",{name:"Review Result"}));
    expect(await screen.findByText("Backend tests — FAIL — 1 failed")).toBeInTheDocument();expect(screen.getByText("Schema certification:").parentElement).toHaveTextContent("FAIL");expect(screen.getByRole("button",{name:"Verify Implementation"})).toBeEnabled();
  });

  it("keeps completed implementation evidence available read-only",async()=>{
    const brief:any={version:1,request:"Completed task",scope:"GLOBAL",whyImplementationIsRequired:"Code",desiredBehavior:"Do it",protectedAuthorities:[],acceptanceCriteria:[],regressionBoundaries:[],proposedVerification:[],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    const item:any={workItemId:"implemented-result",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Completed task",status:"IMPLEMENTED",classification:"CODE",classificationRationale:"Code",analysis:{implementationBrief:brief},linkedInstructionId:null,linkedFutureTaskId:"task",createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:"2026-09-10T00:10:00Z",implementation:{brief,execution:{execution_id:"exec",task_id:"task",status:"COMPLETED",completed_at:"2026-09-10T00:10:00Z",final_report:{summary:"Completed safely",filesModified:["app/completed.py"],tests:["Focused tests passed"]}}}};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):String(input).endsWith("/implementation")?response(item):response({items:[item]}));
    renderPage("/training/ai-training?tab=queue");fireEvent.click(await screen.findByRole("button",{name:"Implemented"}));fireEvent.click(await screen.findByRole("button",{name:"View Implementation"}));
    expect(await screen.findByText("Completed safely")).toBeInTheDocument();expect(screen.getByText("app/completed.py")).toBeInTheDocument();expect(screen.queryByRole("button",{name:"Verify Implementation"})).not.toBeInTheDocument();
    expect(screen.queryByRole("region",{name:"Implementation failure"})).not.toBeInTheDocument();
  });

  it("preserves the bounded failure review state",async()=>{
    const brief:any={version:1,request:"Failed task",scope:"GLOBAL",whyImplementationIsRequired:"Code",desiredBehavior:"Do it",protectedAuthorities:[],acceptanceCriteria:[],regressionBoundaries:[],proposedVerification:[],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    const item:any={workItemId:"failed-result",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Failed task",status:"IMPLEMENTATION_FAILED",classification:"CODE",classificationRationale:"Code",analysis:{implementationBrief:brief},linkedInstructionId:null,linkedFutureTaskId:"task",createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null,implementation:{brief,execution:{execution_id:"exec",task_id:"task",status:"FAILED",failure_reason:"Backend tests failed.",completed_at:"2026-09-10T00:10:00Z",final_report:{summary:"No changes applied",tests:[{name:"Backend tests",status:"FAIL",count:"1 failed"}],build:"FAIL"}}}};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):String(input).endsWith("/implementation")?response(item):response({items:[item]}));
    renderPage("/training/ai-training?tab=queue");fireEvent.click(await screen.findByRole("button",{name:"Review Failure"}));
    expect(await screen.findByText("Backend tests failed.")).toBeInTheDocument();expect(screen.getByText("No changes applied")).toBeInTheDocument();expect(screen.getByText("Backend tests — FAIL — 1 failed")).toBeInTheDocument();expect(screen.getByText("Production build:").parentElement).toHaveTextContent("FAIL");expect(screen.getByText("FAILED · exec")).toBeInTheDocument();expect(screen.getByRole("link",{name:"View Job"})).toHaveAttribute("href","/agents/developer");expect(screen.getByRole("button",{name:"Prepare Retry"})).toBeInTheDocument();expect(screen.queryByRole("button",{name:"Verify Implementation"})).not.toBeInTheDocument();
  });

  it("shows the safe fallback when a canonical failed execution has no reason or final report",async()=>{
    const brief:any={version:1,request:"Failed task",scope:"GLOBAL",whyImplementationIsRequired:"Code",desiredBehavior:"Do it",protectedAuthorities:[],acceptanceCriteria:[],regressionBoundaries:[],proposedVerification:[],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    const item:any={workItemId:"failed-no-reason",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Failed task",status:"IMPLEMENTATION_FAILED",classification:"CODE",classificationRationale:"Code",analysis:{implementationBrief:brief},linkedInstructionId:null,linkedFutureTaskId:"task",createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null,implementation:{brief,execution:{execution_id:"exec-2",task_id:"task",status:"FAILED",failure_reason:null,completed_at:"2026-09-10T00:10:00Z",final_report:null}}};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):String(input).endsWith("/implementation")?response(item):response({items:[item]}));
    renderPage("/training/ai-training?tab=queue");fireEvent.click(await screen.findByRole("button",{name:"Review Failure"}));
    expect(await screen.findByRole("region",{name:"Implementation failure"})).toHaveTextContent("Failure details unavailable.");expect(screen.getByText("FAILED · exec-2")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Prepare Retry"})).toBeInTheDocument();
  });

  it("renders the canonical failure reason when a failed execution has no final report",async()=>{
    const brief:any={version:1,request:"Build task",scope:"GLOBAL",whyImplementationIsRequired:"Code",desiredBehavior:"Do it",protectedAuthorities:[],acceptanceCriteria:[],regressionBoundaries:[],proposedVerification:[],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    const item:any={workItemId:"failed-build",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Build task",status:"IMPLEMENTATION_FAILED",classification:"CODE",classificationRationale:"Code",analysis:{implementationBrief:brief},linkedInstructionId:null,linkedFutureTaskId:"task",createdAt:"2026-09-10T00:00:00Z",updatedAt:"2026-09-10T00:00:00Z",completedAt:null,implementation:{brief,execution:{execution_id:"exec-build",task_id:"task",status:"FAILED",failure_reason:"Production build failed.",completed_at:"2026-09-10T00:10:00Z",final_report:null}}};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):String(input).endsWith("/implementation")?response(item):response({items:[item]}));
    renderPage("/training/ai-training?tab=queue");fireEvent.click(await screen.findByRole("button",{name:"Review Failure"}));
    expect(await screen.findByRole("region",{name:"Implementation failure"})).toHaveTextContent("Production build failed.");expect(screen.getByText("FAILED · exec-build")).toBeInTheDocument();expect(screen.getByRole("link",{name:"View Job"})).toHaveAttribute("href","/agents/developer");expect(screen.getByRole("button",{name:"Prepare Retry"})).toBeInTheDocument();
  });

  it("shows bounded newest-first attempt history without cross-attempt evidence leakage",async()=>{
    const brief:any={version:2,request:"Retry task",scope:"GLOBAL",whyImplementationIsRequired:"Code",desiredBehavior:"Do it",protectedAuthorities:[],acceptanceCriteria:[],regressionBoundaries:[],proposedVerification:[],repository:"C:\\Creator-OS-React",branch:"react-migration"};
    const failedExecution:any={execution_id:"exec-1",task_id:"task-1",status:"FAILED",started_at:"2026-09-10T00:00:00Z",completed_at:"2026-09-10T00:02:00Z",failure_reason:"Production build failed.",final_report:null,review_status:"PENDING"};
    const currentExecution:any={execution_id:"exec-2",task_id:"task-2",status:"COMPLETED",started_at:"2026-09-10T00:03:00Z",completed_at:"2026-09-10T00:05:00Z",failure_reason:null,final_report:{summary:"Retry completed",filesModified:["app/retry.py"],tests:["Focused tests passed"]},review_status:"PENDING"};
    const attempts:any[]=[
      {attemptId:"attempt-2",attemptNumber:2,briefVersion:2,taskId:"task-2",executionId:"exec-2",status:"NEEDS_VERIFICATION",approvedAt:null,startedAt:null,completedAt:"2026-09-10T00:05:00Z",verifiedAt:null,createdAt:null,updatedAt:null,isCurrent:true,execution:currentExecution},
      {attemptId:"attempt-1",attemptNumber:1,briefVersion:1,taskId:"task-1",executionId:"exec-1",status:"FAILED",approvedAt:null,startedAt:null,completedAt:"2026-09-10T00:02:00Z",verifiedAt:null,createdAt:null,updatedAt:null,isCurrent:false,execution:failedExecution},
    ];
    const item:any={workItemId:"retry-history",scope:"GLOBAL",customerFanvueUserId:null,originalRequestText:"Retry task",status:"NEEDS_VERIFICATION",classification:"CODE",classificationRationale:"Code",analysis:{implementationBrief:brief},linkedInstructionId:null,linkedFutureTaskId:"task-2",createdAt:"2026-09-10T00:00:00ZZ",updatedAt:"2026-09-10T00:05:00Z",completedAt:null,implementation:{brief,execution:currentExecution,currentAttempt:attempts[0],attempts}};
    vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("/relationships")?response({items:[],nextCursor:null,hasMore:false}):String(input).endsWith("/implementation")?response(item):response({items:[item]}));
    renderPage("/training/ai-training?tab=queue");fireEvent.click(await screen.findByRole("button",{name:"Review Result"}));
    const history=await screen.findByText("Implementation Attempts (2)");fireEvent.click(history);
    const headings=screen.getAllByText(/Attempt [12] ·/).map((element)=>element.textContent);
    expect(headings).toEqual(["Attempt 2 · NEEDS VERIFICATION","Attempt 1 · FAILED"]);
    expect(screen.getByText("Failure:").parentElement).toHaveTextContent("Production build failed.");expect(screen.getAllByRole("link",{name:"View Job"})).toHaveLength(3);
    fireEvent.click(screen.getByText("View Result"));expect(screen.getAllByText("Retry completed").length).toBeGreaterThan(0);expect(screen.getAllByText("app/retry.py").length).toBeGreaterThan(0);
  });
});
