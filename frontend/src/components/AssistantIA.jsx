import { useEffect, useMemo, useState } from "react";
import { Bot, X, Trash2, Send, Sparkles, Paperclip } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { API_BASE_URL } from "../api/config";
import DocumentsRag from "./DocumentsRag";
import ChampSuggestions from "./ChampSuggestions";

const LANGUES = [
  { code: "fr", label: "FR" },
  { code: "en", label: "EN" },
  { code: "ar", label: "ع" },
];

const MODULES = { dashboard:"dashboard", ventes:"ventes", achats:"achats", fournisseurs:"fournisseurs", clients:"clients", stock:"stock", facturation:"facturation", comptabilite:"comptabilite", parametres:"parametres", collaborateurs:"collaborateurs", "roles-permissions":"roles-permissions", "utilisateurs-externes":"utilisateurs-externes" };

function getModule(pathname) {
  const key = pathname.replace(/^\//, "").split("/")[0] || "dashboard";
  return MODULES[key] || "dashboard";
}

const TEXTES = {
  fr: { title:"Assistant IA", placeholder:"Écrivez votre question…", clear:"Effacer", close:"Fermer", send:"Envoyer", welcome:"Bonjour ! Je peux vous guider dans l’ERP et adapter mon aide au module actuel.", context:"Contexte", suggestions:["Créer une commande","Synthèse des ventes","Produits les plus vendus","Top clients"] },
  en: { title:"AI Assistant", placeholder:"Write your question…", clear:"Clear", close:"Close", send:"Send", welcome:"Hello! I can guide you through the ERP and adapt my help to the current module.", context:"Context", suggestions:["Create an order","Sales summary","Top products","Top customers"] },
  ar: { title:"مساعد الذكاء الاصطناعي", placeholder:"اكتب سؤالك…", clear:"مسح", close:"إغلاق", send:"إرسال", welcome:"مرحباً! يمكنني إرشادك داخل منصة ERP وتكييف المساعدة حسب الوحدة الحالية.", context:"السياق", suggestions:["إنشاء طلب","ملخص المبيعات","أكثر المنتجات مبيعاً","أفضل العملاء"] },
};

export default function AssistantIA({ open, onClose }) {
  const { i18n } = useTranslation();
  const location = useLocation();
  const [langue, setLangue] = useState(() => localStorage.getItem("erp_assistant_lang") || "fr");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const [state, setState] = useState({ operation: null, step: null, data: {} });
  const [docsOpen, setDocsOpen] = useState(false);
  const module = useMemo(() => getModule(location.pathname), [location.pathname]);
  const ui = TEXTES[langue];
  const rtl = langue === "ar";

  useEffect(() => { localStorage.setItem("erp_assistant_lang", langue); }, [langue]);
  useEffect(() => {
    if (open && messages.length === 0) setMessages([{ role:"assistant", text:ui.welcome }]);
  }, [open, langue]);
  useEffect(() => {
    if (messages.length) setMessages((old) => old);
  }, [location.pathname]);

  async function envoyer(e) {
    e?.preventDefault();
    const question = input.trim();
    if (!question || sending) return;
    setMessages((m) => [...m, { role:"user", text:question }]);
    setInput(""); setSending(true);
    try {
      const res = await fetch(`${API_BASE_URL}/assistant/chat`, { method:"POST", headers:{ "Content-Type":"application/json", Authorization:`Bearer ${localStorage.getItem("token")}` }, body:JSON.stringify({ message:question, langue, module, state }) });
      const data = await res.json().catch(() => ({}));

      if (data.state) {
        setState(data.state);
      }
      if (!res.ok) throw new Error(data.detail || "assistant_error");
      setMessages((m) => [...m, { role:"assistant", text:data.reply, sources:Array.isArray(data.sources) ? data.sources : [] }]);
    } catch (err) {
      const fallback = langue === "ar" ? "تعذر الاتصال بالمساعد حالياً." : langue === "en" ? "The assistant could not be reached right now." : "Impossible de contacter l’assistant pour le moment.";
      setMessages((m) => [...m, { role:"assistant", text:fallback }]);
    } finally { setSending(false); }
  }

  function effacer() { setMessages([]); setState({ operation: null, step: null, data: {} }); }
  if (!open) return null;

  return <section className={`assistant-panel${rtl ? " assistant-panel--rtl" : ""}`} dir={rtl ? "rtl" : "ltr"} aria-label={ui.title}>
    <header className="assistant-panel__header">
      <div className="assistant-panel__titre"><span className="assistant-panel__icone"><Sparkles size={16}/></span><div><strong>{ui.title}</strong><small>{ui.context}: {module}</small></div></div>
      <div className="assistant-panel__actions"><button type="button" onClick={()=>setDocsOpen(v=>!v)} title="Documents" aria-label="Documents" aria-pressed={docsOpen}><Paperclip size={16}/></button><button type="button" onClick={effacer} title={ui.clear} aria-label={ui.clear}><Trash2 size={16}/></button><button type="button" onClick={onClose} title={ui.close} aria-label={ui.close}><X size={18}/></button></div>
    </header>
    <div className="assistant-panel__langues">{LANGUES.map((l)=><button key={l.code} type="button" className={langue===l.code?"actif":""} onClick={()=>setLangue(l.code)} aria-pressed={langue===l.code}>{l.label}</button>)}</div>
    {docsOpen && <DocumentsRag langue={langue} />}
    <div className="assistant-panel__messages">
      {messages.map((m,i)=><div key={i} className={`assistant-message assistant-message--${m.role}`}><div>{m.text}</div>{m.role==="assistant" && m.sources?.length>0 && <div className="assistant-sources"><strong>{langue==="en"?"Sources":langue==="ar"?"المصادر":"Sources"}</strong>{m.sources.map((source,j)=><details key={`${source.id}-${j}`}><summary>[{j+1}] {source.title} · {source.source}</summary><small>{source.module}</small><p>{source.excerpt}</p></details>)}</div>}</div>)}
      {sending && <div className="assistant-message assistant-message--assistant">…</div>}
      {messages.length <= 1 && <div className="assistant-panel__suggestions">{ui.suggestions.map((s)=><button key={s} type="button" onClick={()=>setInput(s)}>{s}</button>)}</div>}
    </div>
    <form className="assistant-panel__form" onSubmit={envoyer}>
      <ChampSuggestions value={input} onChange={setInput} placeholder={ui.placeholder} ariaLabel={ui.placeholder} langue={langue} module={module} />
      <button type="submit" disabled={!input.trim() || sending} title={ui.send} aria-label={ui.send}><Send size={17}/></button>
    </form>
  </section>;
}
