import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommercePage } from "./CommercePage";

const offering = {
  offeringId:"offer-1",title:"Beach Set",description:"Sunny",offeringType:"PHOTOSET",
  heroAssetId:42,heroUrl:"/thumb/42",assetCount:2,priceMinor:999,currency:"USD",
  primarySalesChannel:"AI_CHAT",status:"DRAFT",publicationId:null,
  publicationStatus:null,provider:null,providerResourceStatus:"UNVERIFIED",
  deliveryUrl:null,updatedAt:"2026-07-24T00:00:00Z",lastError:null,
  telegramVaultStatus:null,telegramVaultPublishedAt:null,telegramVaultLastError:null,
};
const json = (body:unknown, ok=true) => Promise.resolve({ok,json:()=>Promise.resolve(body)} as Response);
const list = {items:[offering],total:1,page:1,pageSize:20,totalPages:1};

afterEach(()=>vi.unstubAllGlobals());

describe("CommercePage",()=>{
  it("renders authoritative summary, filters, and offering cards",async()=>{
    vi.stubGlobal("fetch",vi.fn((input:RequestInfo|URL)=>{
      const url=String(input);
      if(url.endsWith("/summary"))return json({total:4,draft:1,ready:1,live:1,archived:1});
      return json(list);
    }));
    render(<CommercePage/>);
    expect(await screen.findByText("Beach Set")).toBeInTheDocument();
    expect(screen.getByText("$9.99")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByRole("combobox",{name:"Publication status"})).toBeInTheDocument();
  });

  it("creates an offering through asset, type, metadata, channel, and review steps",async()=>{
    const fetch=vi.fn((input:RequestInfo|URL,init?:RequestInit)=>{
      const url=String(input);
      if(init?.method==="POST"&&url.endsWith("/commerce-authoring"))return json(offering);
      if(url.includes("/available-inventory"))return json({items:[
        {assetId:42,displayName:"Image 42",thumbnailUrl:"/thumb/42",mediaType:"image"},
        {assetId:43,displayName:"Image 43",thumbnailUrl:"/thumb/43",mediaType:"image"},
      ]});
      if(url.endsWith("/summary"))return json({total:0,draft:0,ready:0,live:0,archived:0});
      return json({...list,items:[]});
    });
    vi.stubGlobal("fetch",fetch);render(<CommercePage/>);
    fireEvent.click(await screen.findByRole("button",{name:/New Offering/}));
    const dialog=await screen.findByRole("dialog",{name:"New Offering"});
    fireEvent.click(within(dialog).getByText("Image 42"));
    fireEvent.click(within(dialog).getByRole("button",{name:"Next"}));
    expect(within(dialog).getByRole("combobox",{name:"New offering type"})).toHaveValue("SINGLE_IMAGE");
    fireEvent.click(within(dialog).getByRole("button",{name:"Next"}));
    fireEvent.change(within(dialog).getByRole("textbox",{name:"Commerce title"}),{target:{value:"Single Beach Image"}});
    fireEvent.change(within(dialog).getByRole("spinbutton",{name:"Commerce price"}),{target:{value:"9.99"}});
    fireEvent.click(within(dialog).getByRole("button",{name:"Next"}));
    expect(within(dialog).getByText("Telegram Content Vault")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button",{name:"Next"}));
    fireEvent.click(within(dialog).getByRole("button",{name:"Create Offering"}));
    await waitFor(()=>expect(fetch.mock.calls.some(([url,init])=>String(url).endsWith("/commerce-authoring")&&init?.method==="POST")).toBe(true));
  });

  it("renders empty state and confirms archive",async()=>{
    const confirm=vi.spyOn(window,"confirm").mockReturnValue(true);
    const fetch=vi.fn((input:RequestInfo|URL,init?:RequestInit)=>{
      const url=String(input);
      if(init?.method==="POST"&&url.endsWith("/archive"))return json({...offering,status:"ARCHIVED"});
      if(url.endsWith("/summary"))return json({total:1,draft:1,ready:0,live:0,archived:0});
      return json(list);
    });vi.stubGlobal("fetch",fetch);render(<CommercePage/>);
    fireEvent.click(await screen.findByRole("button",{name:"Archive"}));
    expect(confirm).toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("publishes a live offering to Telegram Content Vault",async()=>{
    const live={...offering,status:"READY",publicationStatus:"LIVE",providerResourceStatus:"PRESENT",deliveryUrl:"https://fanvue.example/link"};
    const fetch=vi.fn((input:RequestInfo|URL,init?:RequestInit)=>{
      const url=String(input);
      if(init?.method==="POST"&&url.endsWith("/telegram-content-vault"))return json({status:"PUBLISHED",publishedAt:"2026-07-24T12:00:00Z"});
      if(url.endsWith("/summary"))return json({total:1,draft:0,ready:1,live:1,archived:0});
      return json({...list,items:[live]});
    });
    vi.stubGlobal("fetch",fetch);render(<CommercePage/>);
    fireEvent.click(await screen.findByRole("button",{name:"View"}));
    const dialog=screen.getByRole("dialog",{name:"Beach Set details"});
    fireEvent.change(within(dialog).getByRole("textbox",{name:"Telegram Content Vault marketing text"}),{target:{value:"Limited release"}});
    fireEvent.click(within(dialog).getByRole("button",{name:"Publish to Telegram Content Vault"}));
    await waitFor(()=>expect(fetch.mock.calls.some(([url,init])=>String(url).endsWith("/telegram-content-vault")&&init?.method==="POST")).toBe(true));
    expect(await within(dialog).findByText("Published")).toBeInTheDocument();
  });
});
