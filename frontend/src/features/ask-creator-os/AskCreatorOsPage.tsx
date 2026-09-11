import {FormEvent,useState} from "react";
import {Link} from "react-router-dom";
import {PageHeader} from "../../shared/ui/PageHeader";
import "./ask-creator-os.css";

type Person={personKey:string;displayName:string;username?:string;customerPath?:string;chatPath?:string};
type Answer={answer:string;entities:Person[];choices:Person[];links?:{label:string;path:string}[];tools:{name:string;success:boolean;resultCount:number}[]};
type Turn={question:string;response:Answer};
const starters=["Who are my top spenders?","Who chats the most but hasn't purchased?","What content sells best?","How much did I make this month?"];

export function AskCreatorOsPage(){
 const [question,setQuestion]=useState("");const [turns,setTurns]=useState<Turn[]>([]);const [loading,setLoading]=useState(false);const [error,setError]=useState("");
 const submit=async(value=question,selectedPersonKey?:string)=>{const text=value.trim();if(!text)return;setLoading(true);setError("");try{const response=await fetch("/api/v1/ask-creator-os",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:text,selectedPersonKey,context:turns.slice(-6).map(turn=>({question:turn.question,answer:turn.response.answer,entities:turn.response.entities}))})});const body=await response.json();if(!response.ok)throw new Error(body.detail||"Creator_OS intelligence is unavailable.");setTurns(current=>[...current,{question:text,response:body}]);setQuestion("");}catch(reason){setError(reason instanceof Error?reason.message:"Creator_OS intelligence is unavailable.");}finally{setLoading(false)}};
 const last=turns.at(-1);
 return <main className="ask-creator-os"><PageHeader title="Ask Creator_OS" description="Ask questions about Ava's business using Creator_OS intelligence."/>
  <section aria-label="Ask Creator_OS conversation" className="ask-workspace">
   <div className="ask-transcript" aria-live="polite">{!turns.length?<div className="ask-starter"><h2>What would you like to know?</h2><div>{starters.map(value=><button key={value} onClick={()=>void submit(value)} type="button">{value}</button>)}</div></div>:turns.map((turn,index)=><article key={`${index}-${turn.question}`}><p><strong>You</strong>{turn.question}</p><div><strong>Creator_OS</strong><p>{turn.response.answer}</p>{turn.response.entities.map(person=><nav key={person.personKey}>{person.customerPath&&<Link to={person.customerPath}>View Customer</Link>}{person.chatPath&&<Link to={person.chatPath}>View Chat</Link>}</nav>)}{turn.response.links?.length?<nav>{turn.response.links.map(link=><Link key={`${link.label}-${link.path}`} to={link.path}>{link.label}</Link>)}</nav>:null}</div></article>)}
   {last?.response.choices?.length?<div className="ask-choices">{last.response.choices.map(person=><button key={person.personKey} onClick={()=>void submit(last.question,person.personKey)} type="button">{person.displayName}{person.username?` @${person.username}`:""}</button>)}</div>:null}
   {loading&&<p className="ask-status" role="status">Creator_OS is thinking…</p>}{error&&<div className="ask-error" role="alert">{error}<button onClick={()=>void submit()} type="button">Retry</button></div>}</div>
   <form className="ask-composer" onSubmit={(event:FormEvent)=>{event.preventDefault();void submit();}}><label>Ask anything about Ava&apos;s business...<textarea disabled={loading} maxLength={1000} onChange={event=>setQuestion(event.target.value)} placeholder="Type your question" value={question}/></label><button disabled={loading||!question.trim()} type="submit">Ask</button></form>
  </section>
 </main>;
}
