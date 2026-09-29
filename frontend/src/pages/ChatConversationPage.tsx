import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { EscalationBanner, formatMessage, type MessageData } from "../lib/novaChat";

type Message = { role:"user"|"assistant"; text:string; language?:string; modality?:string; created_at?:string|null; data?:MessageData; sender_type?:string; sender_name?:string };
export default function ChatConversationPage(){
  const { sessionId } = useParams(); const nav=useNavigate(); const {user}=useAuth();
  const [messages,setMessages]=useState<Message[]>([]); const [error,setError]=useState(""); const [loading,setLoading]=useState(true);
  useEffect(()=>{ if(!sessionId)return; const load=async()=>{try{setMessages(await api<Message[]>("/api/nova/assistant/history",{query:{session_id:sessionId}}));setError("");}catch(e){setError(errorMessage(e));}finally{setLoading(false)}}; void load(); const timer=window.setInterval(()=>void load(),5000); return()=>window.clearInterval(timer); },[sessionId]);
  const initials=(user?.full_name||"U").split(" ").map(x=>x[0]).slice(0,2).join("").toUpperCase();
  return <div className="conversation-page"><div className="customer-page-heading"><div><p className="customer-kicker">Saved conversation</p><h1>{messages[0]?.text?.slice(0,55)||"Conversation"}</h1><p>Full transcript from your PakSim support conversation.</p></div><button className="customer-button secondary" onClick={()=>nav("/chat-history")}>← Back to history</button></div>
    {error&&<div className="customer-error">{error}</div>}
    <section className="saved-chat-card"><div className="saved-chat-head"><div className="nova-identity"><div className="nova-avatar-image">N</div><div><strong>Nova</strong><span>PakSim AI Support</span></div></div><button className="customer-button primary" onClick={()=>nav("/")}>＋ New chat</button></div>
      <div className="saved-transcript">{loading?<div className="customer-loading">Loading conversation…</div>:messages.length===0?<div className="customer-empty compact">No messages found.</div>:messages.map((m,i)=><div key={i} className={`chat-message-row ${m.role}`}><div className={`chat-avatar ${m.sender_type==='agent'?'agent-avatar':m.role==='assistant'?'ai-avatar':'user-avatar'}`}>{m.sender_type==='agent'?'A':m.role==='assistant'?'N':initials}</div><div className="chat-bubble-wrap"><span className="chat-speaker">{m.sender_type==='agent'?(m.sender_name||'Support Agent'):m.role==='assistant'?'Nova':'You'}</span><div className="chat-bubble">{m.role==='assistant'&&m.sender_type!=='agent'?formatMessage(m.text):m.text}</div>{m.role==='assistant'&&m.sender_type!=='agent'&&<EscalationBanner data={m.data} />}<small>{m.created_at?new Date(m.created_at).toLocaleString():""}</small></div></div>)}</div>
    </section>
  </div>
}
