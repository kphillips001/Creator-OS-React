import {render,screen} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import {afterEach,expect,it,vi} from "vitest";
import {BusinessSalesPage} from "./BusinessSalesPage";

afterEach(()=>vi.restoreAllMocks());
it("opens the retained Offers diagnostic route directly",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue({ok:true,json:()=>Promise.resolve({items:[{offerId:"offer-1",decisionId:null,customerId:null,productId:null,assetId:null,offerType:null,price:null,generatedAt:null,presentedAt:null,state:"PRESENTED",states:["PRESENTED"],deliveryState:"CONFIRMED",purchased:false,refunded:false,revenueCents:0,attributionState:"none",attention:false,warnings:[],dataStatus:"complete"}],total:1,page:1,pageSize:24,totalPages:1})} as Response);
  render(<MemoryRouter initialEntries={["/business/sales?tab=offers"]}><BusinessSalesPage/></MemoryRouter>);
  expect(await screen.findByText("offer-1")).toBeInTheDocument();
  expect(screen.getByText("Advanced sales diagnostics")).toBeInTheDocument();
  expect(screen.getByRole("link",{name:/Back to Overview/})).toHaveAttribute("href","/home");
});
