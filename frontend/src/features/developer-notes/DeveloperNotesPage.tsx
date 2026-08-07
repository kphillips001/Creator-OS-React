import { useEffect, useState } from "react";
import { PageHeader } from "../../shared/ui/PageHeader";
import { developerNotesApi, type DeveloperTodo } from "../../infrastructure/api/developerNotesApi";
import "./developerNotes.css";

const localDate = (value: string) => new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", year: "numeric",
}).format(new Date(value));
const ordered = (items: DeveloperTodo[]) => [...items].sort((a,b) => Number(a.completed)-Number(b.completed) || new Date(b.createdAt).getTime()-new Date(a.createdAt).getTime());

export function DeveloperNotesPage() {
  const [todos,setTodos]=useState<DeveloperTodo[]>([]); const [loading,setLoading]=useState(true); const [saving,setSaving]=useState<string|null>(null); const [error,setError]=useState("");
  const [creating,setCreating]=useState(false); const [newTitle,setNewTitle]=useState(""); const [newNote,setNewNote]=useState("");
  const [editingNote,setEditingNote]=useState<string|null>(null); const [noteDraft,setNoteDraft]=useState("");
  useEffect(()=>{ void developerNotesApi.list().then(value=>setTodos(ordered(value.items))).catch((reason:unknown)=>setError(reason instanceof Error?reason.message:"Unable to load Developer TODOs.")).finally(()=>setLoading(false)); },[]);
  const replace=(updated:DeveloperTodo)=>setTodos(items=>ordered(items.map(item=>item.id===updated.id?updated:item)));
  const toggle=async(todo:DeveloperTodo)=>{ setSaving(todo.id);setError("");try{replace(await developerNotesApi.update(todo.id,{completed:!todo.completed}));}catch(reason){setError(reason instanceof Error?reason.message:"Unable to update Developer TODO.");}finally{setSaving(null);} };
  const saveNote=async(todo:DeveloperTodo)=>{setSaving(todo.id);setError("");try{replace(await developerNotesApi.update(todo.id,{note:noteDraft}));setEditingNote(null);}catch(reason){setError(reason instanceof Error?reason.message:"Unable to save note.");}finally{setSaving(null);}};
  const create=async()=>{if(!newTitle.trim())return;setSaving("new");setError("");try{const todo=await developerNotesApi.create(newTitle.trim(),newNote.trim());setTodos(items=>ordered([...items,todo]));setCreating(false);setNewTitle("");setNewNote("");}catch(reason){setError(reason instanceof Error?reason.message:"Unable to create TODO.");}finally{setSaving(null);}};

  return <section className="developer-notes-page"><PageHeader title="Developer Notes" description="Keep track of future Creator_OS development work." />
    <section className="developer-todos" aria-labelledby="developer-todos-title"><header><div><h2 id="developer-todos-title">TODO</h2><p>A simple persistent development checklist.</p></div><button onClick={()=>setCreating(true)} type="button">+ New TODO</button></header>
      {error&&<p className="developer-todos__error" role="alert">{error}</p>}
      {creating&&<div className="developer-todo-editor developer-todo-editor--new"><label>Title<input autoFocus value={newTitle} onChange={event=>setNewTitle(event.target.value)} /></label><label>Note <span>Optional</span><textarea rows={3} value={newNote} onChange={event=>setNewNote(event.target.value)} /></label><div><button disabled={!newTitle.trim()||saving==="new"} onClick={()=>void create()} type="button">Add TODO</button><button onClick={()=>{setCreating(false);setNewTitle("");setNewNote("");}} type="button">Cancel</button></div></div>}
      {loading?<p className="developer-todos__loading">Loading TODOs…</p>:<ul>{todos.map(todo=><li className={todo.completed?"developer-todo developer-todo--completed":"developer-todo"} key={todo.id}>
        <div className="developer-todo__main"><label><input aria-label={`Mark ${todo.title} ${todo.completed?"open":"complete"}`} checked={todo.completed} disabled={saving===todo.id} onChange={()=>void toggle(todo)} type="checkbox"/><span><strong>{todo.title}</strong><small>Added {localDate(todo.createdAt)}</small></span></label>{todo.completed&&todo.completedAt&&<span className="developer-todo__completed-date">Completed {localDate(todo.completedAt)}</span>}</div>
        {todo.note&&editingNote!==todo.id&&<p className="developer-todo__note">{todo.note}</p>}
        {editingNote===todo.id?<div className="developer-todo-editor"><textarea aria-label={`Note for ${todo.title}`} autoFocus rows={3} value={noteDraft} onChange={event=>setNoteDraft(event.target.value)}/><div><button disabled={saving===todo.id} onClick={()=>void saveNote(todo)} type="button">Save</button><button onClick={()=>setEditingNote(null)} type="button">Cancel</button></div></div>:<button className="developer-todo__note-action" onClick={()=>{setEditingNote(todo.id);setNoteDraft(todo.note||"");}} type="button">{todo.note?"Edit Note":"Add Note"}</button>}
      </li>)}</ul>}
    </section>
  </section>;
}
