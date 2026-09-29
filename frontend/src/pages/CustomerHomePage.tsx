import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { EscalationBanner, formatMessage, type MessageData } from "../lib/novaChat";

type AssistantResult = {
  reply: string;
  transcript?: string;
  session_id?: string;
  data?: MessageData;
};

type Message = { role: "user" | "assistant"; text: string; modality?: string; created_at?: string | null; data?: MessageData; sender_type?: string; sender_name?: string };

const langHints: Record<string, string> = { English: "English", Urdu: "Urdu", "Roman Urdu": "Roman Urdu", Sindhi: "Sindhi" };
const starters = [
  "Meri SIM kaam nahi kar rahi",
  "Network / signal nahi aa raha",
  "Internet / data nahi chal raha",
  "Calls nahi ho rahi",
  "Recharge ke baad balance show nahi ho raha",
  "Package activate nahi hua",
  "Mera phone/SIM kho gaya — urgent block chahiye",
  "Complaint status check karna hai",
];

export default function CustomerHomePage() {
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const [msg, setMsg] = useState("");
  const [lang, setLang] = useState(() => localStorage.getItem("paksim_preferred_language") || "Roman Urdu");
  const [voiceEnabled, setVoiceEnabled] = useState(() => localStorage.getItem("paksim_voice_enabled") !== "0");
  const [speaking, setSpeaking] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("paksim_assistant_session") || "");
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => { localStorage.setItem("paksim_preferred_language", lang); }, [lang]);
  useEffect(() => { localStorage.setItem("paksim_voice_enabled", voiceEnabled ? "1" : "0"); if (!voiceEnabled) { window.speechSynthesis?.cancel(); setSpeaking(false); } }, [voiceEnabled]);
  useEffect(() => { if (sessionId) localStorage.setItem("paksim_assistant_session", sessionId); }, [sessionId]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const loadSession = async (id: string) => {
    try {
      const data = await api<Message[]>("/api/nova/assistant/history", { query: { session_id: id } });
      setMessages(data || []);
    } catch (e) { setError(errorMessage(e)); }
  };

  useEffect(() => {
    if (searchParams.get("new") === "1") {
      localStorage.removeItem("paksim_assistant_session");
      setSessionId("");
      setMessages([]);
      setMsg("");
      setError("");
      setSearchParams({}, { replace: true });
      window.setTimeout(() => composerRef.current?.focus(), 120);
      return;
    }
    if (sessionId) void loadSession(sessionId);
  }, []);

  // Keep the customer's chat view in sync when an agent replies to the same complaint thread.
  useEffect(() => {
    if (!sessionId) return;
    const timer = window.setInterval(() => {
      if (!busy) void loadSession(sessionId);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [sessionId, busy]);

  const speak = (text: string) => {
    if (!window.speechSynthesis || !text) return;
    if (!voiceEnabled) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    u.lang = lang === "Urdu" ? "ur-PK" : lang === "Roman Urdu" ? "en-IN" : lang === "Sindhi" ? "sd-PK" : "en-US";
    const voice = window.speechSynthesis.getVoices().find(v => v.lang.toLowerCase().startsWith(u.lang.split("-")[0]));
    if (voice) u.voice = voice;
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  };

  const submit = async (override?: string) => {
    const text = (override ?? msg).trim();
    if (!text || busy) return;
    setBusy(true); setError("");
    setMessages(prev => [...prev, { role: "user", text }]);
    try {
      const form = new FormData();
      form.append("text", text); form.append("modality", "text");
      if (sessionId) form.append("session_id", sessionId);
      const result = await api<AssistantResult>("/api/nova/assistant/message", { method: "POST", formData: form });
      if (result.session_id) setSessionId(result.session_id);
      setMsg("");
      setMessages(prev => [...prev, { role: "assistant", text: result.reply || "", data: result.data }]);
      if (voiceEnabled) speak(result.reply || "");
    } catch (e) {
      setMessages(prev => prev.slice(0, -1)); setError(errorMessage(e));
    } finally { setBusy(false); }
  };

  const startVoice = async () => {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { setError("Voice recording is not supported by this browser."); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks.current = [];
      const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/ogg";
      const mr = new MediaRecorder(stream, { mimeType: mime });
      recorder.current = mr;
      mr.ondataavailable = e => { if (e.data.size) chunks.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunks.current, { type: mime });
        const ext = mime.includes("ogg") ? "ogg" : "webm";
        const form = new FormData();
        form.append("audio", new File([blob], `paksim-voice.${ext}`, { type: mime }));
        form.append("language_hint", langHints[lang]);
        if (sessionId) form.append("session_id", sessionId);
        setBusy(true);
        try {
          const result = await api<AssistantResult>("/api/nova/assistant/voice", { method: "POST", formData: form });
          if (result.session_id) setSessionId(result.session_id);
          if (result.transcript) { const transcriptText = result.transcript; setMessages(prev => [...prev, { role: "user", text: transcriptText, modality: "voice" }]); }
          if (result.reply) { setMessages(prev => [...prev, { role: "assistant", text: result.reply, data: result.data }]); if (voiceEnabled) speak(result.reply); }
        } catch (e) { setError(errorMessage(e)); }
        finally { setBusy(false); }
      };
      mr.start(); setRecording(true);
    } catch (e) { setError(errorMessage(e)); }
  };

  const stopVoice = () => { recorder.current?.stop(); recorder.current = null; setRecording(false); };
  const newChat = () => { localStorage.removeItem("paksim_assistant_session"); setSessionId(""); setMessages([]); setMsg(""); setError(""); };
  const initials = (user?.full_name || "U").split(" ").map(x => x[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="customer-chat-page">
      <div className="chat-page-topbar">
        <div>
          <p className="customer-kicker">PakSim Customer Support</p>
          <h1>How can we help you today, {user?.full_name?.split(" ")[0] || "there"}?</h1>
          <p>Chat with Nova for SIM, account, internet and security support.</p>
        </div>
      </div>

      <section className="customer-chat-card big-chat-window">
        <div className="big-chat-header">
          <div className="nova-identity">
            <div className="nova-avatar-image" aria-label="Nova AI avatar">N</div>
            <div><strong>Nova</strong><span>PakSim AI Support · Online</span></div>
          </div>
          <div className="big-chat-tools">
            <span className={`nova-speaking-pill ${speaking ? "is-speaking" : ""}`}><i />{speaking ? "Nova is speaking" : voiceEnabled ? "Voice ready" : "Voice off"}</span>
            <label>Language
              <select value={lang} onChange={e => setLang(e.target.value)}>
                <option>Roman Urdu</option><option>English</option><option>Urdu</option><option>Sindhi</option>
              </select>
            </label>
            <button className={`voice-control ${voiceEnabled ? "on" : "off"}`} onClick={() => setVoiceEnabled(v => !v)}>{voiceEnabled ? "🔊 Voice ON" : "🔇 Voice OFF"}</button>
            {speaking && <button className="voice-control stop" onClick={() => { window.speechSynthesis?.cancel(); setSpeaking(false); }}>⏹ Stop voice</button>}
            <button className="customer-link-button" onClick={newChat}>＋ New chat</button>
          </div>
        </div>

        <div className="conversation-area">
          {messages.length === 0 && (
            <div className="chat-welcome">
              <div className="nova-avatar-image large">N</div>
              <h2>Assalam-o-Alaikum! Main Nova hoon.</h2>
              <p>
                PakSim telecom support assistant — SIM, network, calls, internet, packages, recharge aur security.
                Main troubleshooting guide karta hoon, policy-based jawab deta hoon, aur zarurat par real complaint ticket banata hoon.
                OTP, password ya card details kabhi share na karein.
              </p>
              <div className="starter-grid">{starters.map(s => <button key={s} type="button" onClick={() => void submit(s)}>{s}<span>→</span></button>)}</div>
            </div>
          )}
          {messages.map((m, i) => {
            const isLastAssistant = m.role === "assistant" && i === messages.length - 1;
            const chips = isLastAssistant && !busy ? (m.data?.clarification_questions || []) : [];
            return (
              <div key={`${m.created_at || "x"}-${i}`} className={`chat-message-row ${m.sender_type === "agent" ? "assistant agent-message-row" : m.role}`}>
                {m.sender_type === "agent" ? <div className="chat-avatar agent-avatar">A</div> : m.role === "assistant" ? <div className="chat-avatar ai-avatar">N</div> : <div className="chat-avatar user-avatar">{initials}</div>}
                <div className="chat-bubble-wrap">
                  <span className="chat-speaker">{m.sender_type === "agent" ? (m.sender_name || "Support Agent") : m.role === "assistant" ? "Nova" : "You"}</span>
                  <div className="chat-bubble">{m.role === "assistant" && m.sender_type !== "agent" ? formatMessage(m.text) : m.text}</div>
                  {m.role === "assistant" && m.sender_type !== "agent" && m.data && <EscalationBanner data={m.data} />}
                  {chips.length > 0 && (
                    <div className="clarify-chip-row">
                      {chips.map((q, qi) => <button key={qi} className="clarify-chip" onClick={() => void submit(q)} disabled={busy}>{q}</button>)}
                    </div>
                  )}
                  {m.role === "assistant" && <div className="message-actions"><button className="tiny-action" onClick={() => voiceEnabled ? speak(m.text) : setVoiceEnabled(true)}>🔊 Read aloud</button>{speaking && i === messages.length - 1 && <button className="tiny-action stop-action" onClick={() => { window.speechSynthesis?.cancel(); setSpeaking(false); }}>⏹ Stop</button>}</div>}
                </div>
              </div>
            );
          })}
          {busy && <div className="chat-message-row assistant"><div className="chat-avatar ai-avatar">N</div><div><span className="chat-speaker">Nova</span><div className="chat-bubble typing"><i></i><i></i><i></i></div></div></div>}
          <div ref={bottomRef} />
        </div>

        {error && <div className="customer-error">{error}</div>}
        <div className="chat-composer-large">
          <textarea ref={composerRef} value={msg} onChange={e => setMsg(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(); } }} placeholder="Write your message to Nova…" rows={3} />
          <div className="chat-composer-bottom"><span>Enter to send · Shift+Enter for new line</span><div>
            {!recording ? <button className="customer-button secondary" onClick={() => void startVoice()} disabled={busy}>🎙 Voice</button> : <button className="customer-button recording" onClick={stopVoice}>⏹ Stop & send</button>}
            <button className="customer-button primary" onClick={() => void submit()} disabled={busy || !msg.trim()}>{busy ? "Thinking…" : "Send →"}</button>
          </div></div>
        </div>
      </section>

    </div>
  );
}
