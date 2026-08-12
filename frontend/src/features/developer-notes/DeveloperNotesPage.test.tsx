import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DeveloperNotesPage } from "./DeveloperNotesPage";

const todo={id:"add-photoshoot-bundle-support",title:"Add Photoshoot Bundle Support",createdAt:"2026-08-07T12:00:00+00:00",completed:false,completedAt:null,note:null};
const response=(body:unknown,status=200)=>Promise.resolve(new Response(JSON.stringify(body),{status,headers:{"content-type":"application/json"}}));

describe("DeveloperNotesPage",()=>{
  afterEach(()=>vi.restoreAllMocks());
  it("shows completion date only while completed and persists reopen",async()=>{
    vi.spyOn(globalThis,"fetch").mockImplementation((_input,init)=>{if(init?.method==="PATCH"){const changes=JSON.parse(String(init.body)) as {completed:boolean};return response({...todo,completed:changes.completed,completedAt:changes.completed?"2026-08-07T15:00:00+00:00":null});}return response({items:[todo]});});
    render(<DeveloperNotesPage/>);expect(await screen.findByText(todo.title)).toBeInTheDocument();expect(screen.getByText("Added Aug 7, 2026")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox",{name:/complete$/}));expect(await screen.findByText("Completed Aug 7, 2026")).toBeInTheDocument();expect(screen.getByText(todo.title).closest("li")).toHaveClass("developer-todo--completed");
    fireEvent.click(screen.getByRole("checkbox",{name:/open$/}));await waitFor(()=>expect(screen.queryByText(/Completed Aug/)).not.toBeInTheDocument());
  });
  it("adds, edits, and clears one persisted note",async()=>{
    let note:string|null=null;vi.spyOn(globalThis,"fetch").mockImplementation((_input,init)=>{if(init?.method==="PATCH"){note=(JSON.parse(String(init.body)) as {note:string}).note.trim()||null;return response({...todo,note});}return response({items:[todo]});});render(<DeveloperNotesPage/>);
    fireEvent.click(await screen.findByRole("button",{name:"Add Note"}));const editor=screen.getByLabelText(`Note for ${todo.title}`);fireEvent.change(editor,{target:{value:"Need sellable bundles."}});expect(editor).toHaveValue("Need sellable bundles.");fireEvent.click(screen.getByRole("button",{name:"Save"}));await waitFor(()=>expect(screen.getByText("Need sellable bundles.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button",{name:"Edit Note"}));fireEvent.change(screen.getByLabelText(`Note for ${todo.title}`),{target:{value:""}});fireEvent.click(screen.getByRole("button",{name:"Save"}));await waitFor(()=>expect(screen.queryByText("Need sellable bundles.")).not.toBeInTheDocument());
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
