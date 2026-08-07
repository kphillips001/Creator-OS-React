import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoGalleryPage } from "./VideoGalleryPage";

const reply=(body:unknown)=>Promise.resolve(new Response(JSON.stringify(body),{status:200,headers:{"content-type":"application/json"}}));
const item={generatedMediaId:"m1",sessionId:"s1",title:"Quiet Light",conceptSummary:"A calm scene",posterUrl:"/poster.jpg",mediaUrl:"/video.mp4",duration:15,resolution:"720p",width:720,height:1280,aspectRatio:"9:16",hasAudio:true,providerId:"wavespeed_seedance_2_0",providerModel:"Seedance 2.0",createdAt:"2026-08-06",sourceType:"generation",sourceId:"g1",sourceLabel:"Generation Library image",sourcePreviewUrl:null,completionStatus:"COMPLETE",assetState:"IN_ASSET_LIBRARY",finalAssetId:42,lineage:{},extensionAvailable:true,alternateGenerationAvailable:true} as const;
const renderPage=()=>render(<MemoryRouter><VideoGalleryPage/></MemoryRouter>);

describe("VideoGalleryPage",()=>{
  afterEach(()=>vi.restoreAllMocks());
  it("renders the canonical empty state",async()=>{vi.spyOn(globalThis,"fetch").mockImplementation(()=>reply({items:[],page:1,pageSize:24,total:0,totalPages:1}));renderPage();expect(await screen.findByText("Your completed videos will appear here.")).toBeInTheDocument();expect(screen.getByRole("link",{name:/Open Video Studio/})).toHaveAttribute("href","/studio/video");});
  it("opens a poster card in a playable focused viewer",async()=>{vi.spyOn(globalThis,"fetch").mockImplementation(()=>reply({items:[item],page:1,pageSize:24,total:1,totalPages:1}));renderPage();fireEvent.click(await screen.findByRole("button",{name:/Quiet Light/}));expect(screen.getByText("A calm scene")).toBeInTheDocument();expect(document.querySelector("video")).toHaveAttribute("src","/video.mp4");expect(screen.getByRole("link",{name:/In Asset Library/})).toBeInTheDocument();});
  it("provides canonical extension and alternate deep links",async()=>{vi.spyOn(globalThis,"fetch").mockImplementation(()=>reply({items:[item],page:1,pageSize:24,total:1,totalPages:1}));renderPage();fireEvent.click(await screen.findByRole("button",{name:/Quiet Light/}));fireEvent.click(screen.getByRole("button",{name:/Extend Video/}));expect(window.location.pathname).toBe("/");});
});
