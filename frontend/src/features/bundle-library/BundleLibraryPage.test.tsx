import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { BundleLibraryPage } from "./BundleLibraryPage";

const bundle=(published=false)=>({offeringId:"offer-1",title:"Midnight Set",source:"BUNDLE_STUDIO",sourceId:"bundle-1",status:"READY",readinessStatus:"READY",destination:"WALL",priceMinor:1499,currency:"USD",memberCount:3,members:[1,2,3].map((assetId,index)=>({assetId,position:index+1,imageUrl:`/thumb/${assetId}`})),heroImageUrl:"/hero",deliveryUrl:"https://fanvue.test/link",contentVaultPublication:{status:published?"PUBLISHED":"NOT_PUBLISHED",canPublish:!published,configured:true},preparation:{status:"READY",statusLabel:"Paid Bundle Ready",contentVaultCaption:null,promotionalTeaser:{status:"READY",previewUrl:"/teaser"}}});
const response=(value:unknown)=>Promise.resolve(new Response(JSON.stringify(value),{status:200,headers:{"Content-Type":"application/json"}}));
afterEach(()=>vi.restoreAllMocks());

it("renders canonical price, count, and authoritative posted Wall badge",async()=>{
 vi.spyOn(globalThis,"fetch").mockImplementation(()=>response({bundles:[bundle(true)]}));render(<BundleLibraryPage/>);
 expect(await screen.findByRole("heading",{name:"Midnight Set"})).toBeInTheDocument();expect(screen.getByText("3 images · $14.99")).toBeInTheDocument();expect(screen.getByText("✓ WALL")).toBeInTheDocument();
});

it("saves a manual caption without calling caption generation",async()=>{
 const fetch=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>String(input).endsWith("/caption")&&init?.method==="PUT"?response({}):response({bundles:[bundle(false)]}));render(<BundleLibraryPage/>);
 fireEvent.click(await screen.findByRole("heading",{name:"Midnight Set"}));fireEvent.change(screen.getByLabelText("Write your own caption"),{target:{value:"Three new photos waiting for you."}});fireEvent.click(screen.getByRole("button",{name:"Save Caption"}));
 await waitFor(()=>expect(fetch).toHaveBeenCalledWith("/api/v1/bundle-studio/commercial-bundles/bundle-1/content-vault/caption",expect.objectContaining({method:"PUT",body:JSON.stringify({text:"Three new photos waiting for you.",source:"MANUAL"})})));
 expect(fetch.mock.calls.some(([url])=>String(url).endsWith("captions/generate"))).toBe(false);
});
