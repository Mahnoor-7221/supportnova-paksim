import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../lib/api";

type Session = { session_id:string; created_at:string|null; title:string; preview:string; language:string; message_count:number };
const languageLabel: Record<string,string> = { en:"English", ur:"Urdu", roman_ur:"Roman Urdu", sd:"Sindhi", Sindhi:"Sindhi" };

export default function ChatHistoryPage(){
  const nav=useNavigate(); const [sessions,setSessions]=useState<Session[]>([]); const [loading,setLoading]=useState(true); const [error,setError]=useState("");
  const load=async()=>{setLoading(true);setError("");try{setSessions(await api<Session[]>("/api/nova/assistant/sessions"));}catch(e){setError(errorMessage(e));}finally{setLoading(false)}};
  useEffect(()=>{void load()},[]);
  return <div className="chat-history-page clean-history-page">
    <div className="customer-page-heading"><div><p className="customer-kicker">Your conversations</p><h1>Chat history</h1><p>Every Nova conversation is kept on its own page so this view stays clean and easy to scan.</p></div><div className="page-heading-actions"><button className="customer-button secondary" onClick={()=>nav("/profile")}>👤 Profile</button><button className="customer-button primary" onClick={()=>nav("/")}>＋ New chat</button></div></div>
    {error&&<div className="customer-error">{error}<button onClick={()=>void load()}>Try again</button></div>}
    <section className="history-page-card"><div className="section-head"><div><strong>Saved conversations</strong><small>{sessions.length} conversation{sessions.length===1?"":"s"}</small></div><button className="customer-link-button" onClick={()=>void load()}>↻ Refresh</button></div>
      {loading?<div className="customer-loading">Loading chat history…</div>:sessions.length===0?<div className="customer-empty"><div className="empty-icon">💬</div><h2>No conversations yet</h2><p>Start a conversation with Nova and your transcript will appear here.</p><button className="customer-button primary" onClick={()=>nav("/")}>Start a chat</button></div>:<div className="history-session-grid">{sessions.map(s=><button className="history-session-row" key={s.session_id} onClick={()=>nav(`/chat-history/${s.session_id}`)}><div className="session-ai-avatar">N</div><div className="history-session-main"><div className="history-session-meta"><span>{s.created_at?new Date(s.created_at).toLocaleString():"Recent"}</span><span>{languageLabel[s.language]||s.language}</span><span>{s.message_count} messages</span></div><strong>{s.title||"Nova conversation"}</strong><p>{s.preview}</p><small>Open full conversation →</small></div></button>)}</div>}
    </section>
  </div>
}
