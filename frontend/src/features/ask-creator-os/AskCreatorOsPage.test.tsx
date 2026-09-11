import {fireEvent,render,screen} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import {afterEach,expect,it,vi} from "vitest";
import {AskCreatorOsPage} from "./AskCreatorOsPage";
afterEach(()=>vi.restoreAllMocks());

it("unifies the starter, transcript, and persistent composer in one card",async()=>{
 let resolveResponse:(value:Response)=>void=()=>undefined;
 const fetchMock=vi.spyOn(globalThis,"fetch").mockImplementation(()=>new Promise(resolve=>{resolveResponse=resolve;}));
 render(<MemoryRouter><AskCreatorOsPage/></MemoryRouter>);
 const workspace=screen.getByRole("region",{name:"Ask Creator_OS conversation"});
 expect(screen.getByRole("heading",{name:"Ask Creator_OS"})).toBeInTheDocument();
 expect(workspace).toContainElement(screen.getByRole("button",{name:"Who are my top spenders?"}));
 expect(workspace).toContainElement(screen.getByLabelText("Ask anything about Ava's business..."));
 expect(document.querySelectorAll(".ask-workspace")).toHaveLength(1);
 expect(document.querySelectorAll(".ask-composer")).toHaveLength(1);
 fireEvent.click(screen.getByRole("button",{name:"Who are my top spenders?"}));
 expect(screen.getByRole("status")).toHaveTextContent("thinking");
 resolveResponse(new Response(JSON.stringify({answer:"1. Mike — $184.50",entities:[{personKey:"telegram:1:2:3",displayName:"Mike",customerPath:"/business/customers?customer=commerce:3",chatPath:"/business/relationships?relationship=telegram:1:2:3"}],choices:[],tools:[{name:"customer_ranking",success:true,resultCount:1}]}),{status:200,headers:{"Content-Type":"application/json"}}));
 expect(await screen.findByText(/Mike — \$184.50/)).toBeInTheDocument();
 expect(screen.queryByText("What would you like to know?")).not.toBeInTheDocument();
 expect(screen.getByLabelText("Ask anything about Ava's business...")).toBeInTheDocument();
 expect(screen.getByRole("link",{name:"View Customer"})).toHaveAttribute("href","/business/customers?customer=commerce:3");
 expect(screen.getByRole("link",{name:"View Chat"})).toHaveAttribute("href","/business/relationships?relationship=telegram:1:2:3");
 expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("keeps safe errors and the integrated composer available for retry",async()=>{
 vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({detail:"Creator_OS intelligence is temporarily unavailable."}),{status:503,headers:{"Content-Type":"application/json"}}));
 render(<MemoryRouter><AskCreatorOsPage/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText("Ask anything about Ava's business..."),{target:{value:"How much did I make today?"}});
 fireEvent.click(screen.getByRole("button",{name:"Ask"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
 expect(screen.getByRole("button",{name:"Retry"})).toBeInTheDocument();
 expect(screen.getByLabelText("Ask anything about Ava's business...")).toBeInTheDocument();
});

it("renders operational deep links inside the unified conversation card",async()=>{
 vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({answer:"Telegram Business: READY.",entities:[],choices:[],links:[{label:"View Operations",path:"/business/operations"}],tools:[{name:"messaging_operations",success:true,resultCount:0}]}),{status:200,headers:{"Content-Type":"application/json"}}));
 render(<MemoryRouter><AskCreatorOsPage/></MemoryRouter>);
 fireEvent.change(screen.getByLabelText("Ask anything about Ava's business..."),{target:{value:"Is Telegram healthy?"}});fireEvent.click(screen.getByRole("button",{name:"Ask"}));
 expect(await screen.findByRole("link",{name:"View Operations"})).toHaveAttribute("href","/business/operations");
});

it("shows ambiguity choices and sends canonical selection",async()=>{
 const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(new Response(JSON.stringify({answer:"I found 2 matching customers.",entities:[],choices:[{personKey:"telegram:1:2:3",displayName:"Mike",username:"one"},{personKey:"telegram:1:2:4",displayName:"Mike",username:"two"}],tools:[]}),{status:200,headers:{"Content-Type":"application/json"}})).mockResolvedValueOnce(new Response(JSON.stringify({answer:"Mike has spent $10.00",entities:[],choices:[],tools:[]}),{status:200,headers:{"Content-Type":"application/json"}}));
 render(<MemoryRouter><AskCreatorOsPage/></MemoryRouter>);fireEvent.change(screen.getByLabelText("Ask anything about Ava's business..."),{target:{value:"What did Mike buy?"}});fireEvent.click(screen.getByRole("button",{name:"Ask"}));
 fireEvent.click(await screen.findByRole("button",{name:"Mike @two"}));
 await vi.waitFor(()=>expect(String(fetchMock.mock.calls[1]![1]?.body)).toContain('"selectedPersonKey":"telegram:1:2:4"'));
});
