import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DeveloperNotesPage } from "./DeveloperNotesPage";

const todo={id:"add-photoshoot-bundle-support",title:"Add Photoshoot Bundle Support",createdAt:"2026-08-07T12:00:00+00:00",completed:false,completedAt:null,note:null};
const response=(body:unknown,status=200)=>Promise.resolve(new Response(JSON.stringify(body),{status,headers:{"content-type":"application/json"}}));

describe("DeveloperNotesPage",()=>{
  afterEach(()=>vi.restoreAllMocks());
  it("keeps the TODO tracker without the retired historical normalization panel",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation(()=>response({items:[todo]}));
    render(<DeveloperNotesPage/>);expect(await screen.findByText(todo.title)).toBeInTheDocument();
    expect(screen.queryByText("Normalize Existing Content Vault Posts")).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Scan Existing Posts"})).not.toBeInTheDocument();
  });
  it("shows completion date only while completed and persists reopen",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation((_input,init)=>{if(init?.method==="PATCH"){const changes=JSON.parse(String(init.body)) as {completed:boolean};return response({...todo,completed:changes.completed,completedAt:changes.completed?"2026-08-07T15:00:00+00:00":null});}return response({items:[todo]});});
    render(<DeveloperNotesPage/>);expect(await screen.findByText(todo.title)).toBeInTheDocument();expect(screen.getByText("Added Aug 7, 2026")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox",{name:/complete$/}));fireEvent.click(screen.getByRole("button",{name:`Toggle ${todo.title}`}));expect(await screen.findByText("Completed Aug 7, 2026")).toBeInTheDocument();expect(screen.getByText(todo.title).closest("li")).toHaveClass("developer-todo--completed");
    fireEvent.click(screen.getByRole("checkbox",{name:/open$/}));await waitFor(()=>expect(screen.queryByText(/Completed Aug/)).not.toBeInTheDocument());
  });
  it("shows persisted subnote date and time while collapsed and edits the parent in place",async()=>{
    const child={id:"child",todoId:todo.id,title:"Created New Instagram model avabthorne",content:"Details",completed:false,createdAt:"2026-08-22T20:14:00Z",updatedAt:"2026-08-22T21:00:00Z"};
    let current={...todo,subnotes:[child]};const fetch=vi.spyOn(globalThis,"fetch").mockImplementation((_input,init)=>{if(init?.method==="PATCH"){const changes=JSON.parse(String(init.body)) as {title:string};current={...current,title:changes.title};return response(current);}return response({items:[current]});});
    const view=render(<DeveloperNotesPage/>);const toggle=await screen.findByRole("button",{name:`Toggle ${todo.title}`});fireEvent.click(toggle);const childToggle=screen.getByRole("button",{name:`Toggle subnote ${child.title}`});expect(childToggle).toHaveAttribute("aria-expanded","false");const expectedDate=new Intl.DateTimeFormat("en-US",{month:"short",day:"numeric",year:"numeric"}).format(new Date(child.createdAt));const expectedTime=new Intl.DateTimeFormat("en-US",{hour:"numeric",minute:"2-digit"}).format(new Date(child.createdAt));expect(screen.getByRole("button",{name:`Mark subnote ${child.title} completed`})).toHaveTextContent(`Added ${expectedDate} · ${expectedTime}`);expect(screen.queryByText("Details")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:`Edit ${todo.title}`}));const editor=screen.getByLabelText(`Title for ${todo.title}`);fireEvent.change(editor,{target:{value:"Temporary title"}});fireEvent.click(screen.getByRole("button",{name:"Cancel"}));expect(screen.getByText(todo.title)).toBeInTheDocument();expect(fetch.mock.calls.some(([,init])=>init?.method==="PATCH")).toBe(false);
    fireEvent.click(screen.getByRole("button",{name:`Edit ${todo.title}`}));fireEvent.change(screen.getByLabelText(`Title for ${todo.title}`),{target:{value:"Launch and Warm Up New Instagram"}});fireEvent.click(screen.getByRole("button",{name:"Save"}));expect(await screen.findByText("Launch and Warm Up New Instagram")).toBeInTheDocument();expect(childToggle).toBeInTheDocument();expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/developer-notes\/todos\/add-photoshoot-bundle-support$/),expect.objectContaining({method:"PATCH",body:JSON.stringify({title:"Launch and Warm Up New Instagram"})}));
    view.unmount();render(<DeveloperNotesPage/>);const refreshed=await screen.findByRole("button",{name:"Toggle Launch and Warm Up New Instagram"});expect(refreshed).toHaveAttribute("aria-expanded","false");fireEvent.click(refreshed);expect(screen.getByRole("button",{name:`Toggle subnote ${child.title}`})).toHaveAttribute("aria-expanded","false");
  });
  it("creates, independently edits, and deletes persistent subnotes",async()=>{
    let subnotes=[{id:"one",todoId:todo.id,title:"Existing Note",content:"Legacy details",completed:false,createdAt:todo.createdAt,updatedAt:todo.createdAt}];
    vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{const url=String(input);if(init?.method==="POST"&&url.endsWith("/subnotes")){const body=JSON.parse(String(init.body)) as {title:string;content:string};const created={id:"two",todoId:todo.id,...body,completed:false,createdAt:todo.createdAt,updatedAt:todo.createdAt};subnotes=[...subnotes,created];return response(created,201);}if(init?.method==="PATCH"&&url.includes("/subnotes/")){const body=JSON.parse(String(init.body)) as {title:string;content:string};subnotes=subnotes.map(note=>note.id==="two"?{...note,...body}:note);return response(subnotes[1]);}if(init?.method==="DELETE"&&url.includes("/subnotes/")){subnotes=subnotes.filter(note=>note.id!==url.split("/").pop());return Promise.resolve(new Response(null,{status:204}));}return response({items:[{...todo,subnotes}]});});render(<DeveloperNotesPage/>);
    fireEvent.click(await screen.findByRole("button",{name:`Toggle ${todo.title}`}));expect(screen.getByRole("button",{name:"Toggle subnote Existing Note"})).toHaveAttribute("aria-expanded","false");expect(screen.queryByText("Legacy details")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"+ Add Subnote"}));fireEvent.change(screen.getByLabelText(`New subnote title for ${todo.title}`),{target:{value:"Second note"}});fireEvent.change(screen.getByLabelText(`New subnote notes for ${todo.title}`),{target:{value:"Independent details"}});fireEvent.click(screen.getByRole("button",{name:"Save"}));
    const second=await screen.findByRole("button",{name:"Toggle subnote Second note"});expect(second).toHaveAttribute("aria-expanded","false");fireEvent.click(screen.getByRole("button",{name:"Edit subnote Second note"}));expect(second).toHaveAttribute("aria-expanded","true");expect(screen.getByLabelText("Title for subnote Second note")).toHaveValue("Second note");expect(screen.getByLabelText("Notes for subnote Second note")).toHaveValue("Independent details");fireEvent.change(screen.getByLabelText("Notes for subnote Second note"),{target:{value:"Changed details"}});fireEvent.click(within(second.closest("li")!).getByRole("button",{name:"Cancel"}));expect(screen.queryByLabelText("Notes for subnote Second note")).not.toBeInTheDocument();expect(screen.getByText("Independent details")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"Edit subnote Second note"}));fireEvent.change(screen.getByLabelText("Notes for subnote Second note"),{target:{value:"Changed details"}});fireEvent.click(within(second.closest("li")!).getByRole("button",{name:"Save"}));await waitFor(()=>expect(second).toHaveAttribute("aria-expanded","false"));
    fireEvent.click(screen.getByRole("button",{name:"Delete subnote Second note"}));fireEvent.click(screen.getByRole("button",{name:/^Delete$/}));await waitFor(()=>expect(screen.queryByRole("button",{name:"Toggle subnote Second note"})).not.toBeInTheDocument());expect(screen.getByRole("button",{name:"Toggle subnote Existing Note"})).toBeInTheDocument();
  });
  it("toggles persisted subnote completion from the title without coupling header controls",async()=>{
    const child={id:"child",todoId:todo.id,title:"Hook up phone via ADB",content:"Keep details",completed:false,createdAt:todo.createdAt,updatedAt:todo.createdAt};
    let current={...todo,subnotes:[child]};
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{const url=String(input);if(init?.method==="PATCH"&&url.endsWith("/completion")){const body=JSON.parse(String(init.body)) as {completed:boolean};current={...current,subnotes:[{...child,completed:body.completed}]};return response(current.subnotes[0]);}return response({items:[current]});});
    const view=render(<DeveloperNotesPage/>);fireEvent.click(await screen.findByRole("button",{name:`Toggle ${todo.title}`}));
    const completion=screen.getByRole("button",{name:`Mark subnote ${child.title} completed`});const row=completion.closest("li")!;const chevron=within(row).getByRole("button",{name:`Toggle subnote ${child.title}`});
    fireEvent.click(completion);await waitFor(()=>expect(row).toHaveClass("developer-subnote--completed"));expect(chevron).toHaveAttribute("aria-expanded","false");
    fireEvent.click(chevron);expect(chevron).toHaveAttribute("aria-expanded","true");expect(fetch).toHaveBeenCalledTimes(2);
    fireEvent.click(within(row).getByRole("button",{name:`Edit subnote ${child.title}`}));expect(screen.getByLabelText(`Title for subnote ${child.title}`)).toBeInTheDocument();expect(fetch).toHaveBeenCalledTimes(2);
    fireEvent.click(within(row).getByRole("button",{name:`Mark subnote ${child.title} active`}));await waitFor(()=>expect(row).not.toHaveClass("developer-subnote--completed"));
    view.unmount();render(<DeveloperNotesPage/>);fireEvent.click(await screen.findByRole("button",{name:`Toggle ${todo.title}`}));expect(screen.getByRole("button",{name:`Mark subnote ${child.title} completed`})).toBeInTheDocument();
  });
  it("starts collapsed, expands independently, and keeps controls isolated",async()=>{
    const second={...todo,id:"second",title:"X Scraping Research",note:"Research details",subnotes:[{id:"research",todoId:"second",title:"Research",content:"Research details",completed:false,createdAt:todo.createdAt,updatedAt:todo.createdAt}]};
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation((_input,init)=>init?.method==="PATCH"?response({...todo,completed:true,completedAt:"2026-08-07T15:00:00Z"}):response({items:[todo,second]}));
    const view=render(<DeveloperNotesPage/>);const firstToggle=await screen.findByRole("button",{name:`Toggle ${todo.title}`});const secondToggle=screen.getByRole("button",{name:"Toggle X Scraping Research"});
    expect(firstToggle).toHaveAttribute("aria-expanded","false");expect(secondToggle).toHaveAttribute("aria-expanded","false");expect(screen.queryByText("Research details")).not.toBeInTheDocument();expect(screen.queryByRole("button",{name:"Add Note"})).not.toBeInTheDocument();
    fireEvent.click(firstToggle);fireEvent.click(secondToggle);expect(firstToggle).toHaveAttribute("aria-expanded","true");expect(secondToggle).toHaveAttribute("aria-expanded","true");expect(screen.queryByText("Research details")).not.toBeInTheDocument();const research=screen.getByRole("button",{name:"Toggle subnote Research"});fireEvent.click(research);expect(screen.getByText("Research details")).toBeInTheDocument();
    fireEvent.click(firstToggle);expect(firstToggle).toHaveAttribute("aria-expanded","false");expect(secondToggle).toHaveAttribute("aria-expanded","true");fireEvent.click(secondToggle);fireEvent.click(secondToggle);expect(screen.getByRole("button",{name:"Toggle subnote Research"})).toHaveAttribute("aria-expanded","false");
    fireEvent.click(screen.getByRole("checkbox",{name:/Add Photoshoot Bundle Support complete$/}));await waitFor(()=>expect(fetch).toHaveBeenCalledWith(expect.any(String),expect.objectContaining({method:"PATCH"})));expect(firstToggle).toHaveAttribute("aria-expanded","false");
    fireEvent.click(screen.getByRole("button",{name:"Delete X Scraping Research"}));expect(secondToggle).toHaveAttribute("aria-expanded","true");fireEvent.click(screen.getByRole("button",{name:"Cancel"}));
    view.unmount();render(<DeveloperNotesPage/>);expect(await screen.findByRole("button",{name:`Toggle ${todo.title}`})).toHaveAttribute("aria-expanded","false");const refreshedSecond=screen.getByRole("button",{name:"Toggle X Scraping Research"});expect(refreshedSecond).toHaveAttribute("aria-expanded","false");fireEvent.click(refreshedSecond);expect(screen.getByRole("button",{name:"Toggle subnote Research"})).toHaveAttribute("aria-expanded","false");
  });
  it("creates a TODO and places incomplete newest items first",async()=>{
    const completed={...todo,id:"old",title:"Old completed",completed:true,completedAt:"2026-08-07T16:00:00Z"};const created={...todo,id:"new",title:"New work",createdAt:"2026-08-07T17:00:00Z",note:"Details"};vi.spyOn(globalThis,"fetch").mockImplementation((_input,init)=>init?.method==="POST"?response(created,201):response({items:[completed,todo]}));render(<DeveloperNotesPage/>);
    fireEvent.click(await screen.findByRole("button",{name:"+ New TODO"}));fireEvent.change(screen.getByLabelText("Title"),{target:{value:"New work"}});fireEvent.change(screen.getByLabelText(/Note Optional/),{target:{value:"Details"}});fireEvent.click(screen.getByRole("button",{name:"Add TODO"}));expect(await screen.findByText("New work")).toBeInTheDocument();
    const titles=screen.getAllByRole("listitem").map(item=>item.querySelector("strong")?.textContent);expect(titles).toEqual(["New work","Add Photoshoot Bundle Support","Old completed"]);
  });
  it("confirms deletion, supports cancel, and removes only the selected TODO durably",async()=>{
    const duplicate={...todo,id:"duplicate",title:"Duplicate TODO",note:"Child note"};let items=[todo,duplicate];
    const fetch=vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{
      if(init?.method==="DELETE"){
        const id=decodeURIComponent(String(input).split("/").pop()!);items=items.filter(item=>item.id!==id);return Promise.resolve(new Response(null,{status:204}));
      }
      return response({items});
    });
    const first=render(<DeveloperNotesPage/>);expect(await screen.findByText("Duplicate TODO")).toBeInTheDocument();
    expect(screen.getAllByTitle("Delete TODO")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button",{name:"Delete Duplicate TODO"}));
    const dialog=screen.getByRole("dialog",{name:"Delete TODO?"});expect(dialog).toHaveTextContent("Are you sure you want to permanently delete this TODO?");expect(dialog).toHaveTextContent("Duplicate TODO");
    fireEvent.click(screen.getByRole("button",{name:"Cancel"}));expect(screen.queryByRole("dialog",{name:"Delete TODO?"})).not.toBeInTheDocument();expect(screen.getByText("Duplicate TODO")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"Delete Duplicate TODO"}));fireEvent.click(screen.getByRole("button",{name:/^Delete$/}));
    await waitFor(()=>expect(screen.queryByText("Duplicate TODO")).not.toBeInTheDocument());expect(screen.getByText(todo.title)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/developer-notes\/todos\/duplicate$/),{method:"DELETE"});
    first.unmount();render(<DeveloperNotesPage/>);expect(await screen.findByText(todo.title)).toBeInTheDocument();expect(screen.queryByText("Duplicate TODO")).not.toBeInTheDocument();
  });
  it("keeps the TODO visible and surfaces an error when deletion fails",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation((_input,init)=>init?.method==="DELETE"?response({detail:"Delete unavailable."},500):response({items:[todo]}));
    render(<DeveloperNotesPage/>);fireEvent.click(await screen.findByRole("button",{name:`Delete ${todo.title}`}));fireEvent.click(screen.getByRole("button",{name:/^Delete$/}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Delete unavailable.");expect(screen.getByText(todo.title)).toBeInTheDocument();
  });
});
