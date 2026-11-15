import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  X, Trash2, Send, Sparkles, Paperclip,
  Mic, MicOff, Volume2, VolumeX, BellRing, Headphones,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../api/config";
import { deconnecter } from "../api/sessionsApi";
import { interpreter } from "../validation/commandesVocales";
import DocumentsRag from "./DocumentsRag";
import ChampSuggestions from "./ChampSuggestions";

const LANGUES = [
  { code: "fr", label: "FR", speech: "fr-FR" },
  { code: "en", label: "EN", speech: "en-US" },
  { code: "ar", label: "ع", speech: "ar-MA" },
];

const MODULES = {
  dashboard: "dashboard", ventes: "ventes", achats: "achats",
  fournisseurs: "fournisseurs", clients: "clients", stock: "stock",
  facturation: "facturation", comptabilite: "comptabilite",
  parametres: "parametres", collaborateurs: "collaborateurs",
  "roles-permissions": "roles-permissions",
  "utilisateurs-externes": "utilisateurs-externes",
};

function getModule(pathname) {
  const key = pathname.replace(/^\//, "").split("/")[0] || "dashboard";
  return MODULES[key] || "dashboard";
}

const TEXTES = {
  fr: {
    title: "Assistant IA", placeholder: "Écrivez votre question…", clear: "Effacer",
    close: "Fermer", send: "Envoyer", welcome: "Bonjour ! Je peux vous guider dans l’ERP et adapter mon aide au module actuel.",
    context: "Contexte", suggestions: ["Créer une commande", "Synthèse des ventes", "Produits les plus vendus", "Top clients"],
    micStart: "Démarrer la saisie vocale", micStop: "Arrêter la saisie vocale",
    voiceOn: "Activer les réponses vocales", voiceOff: "Désactiver les réponses vocales",
    readNotifications: "Lire mes notifications non lues", listening: "Je vous écoute…", conversationOn: "Mode conversation", conversationOff: "Arrêter la conversation", conversationStarted: "Mode conversation activé. Je vous écoute.", conversationStopped: "Mode conversation désactivé.", conversationEnded: "Conversation terminée : aucune parole détectée.", confirmLogout: "Voulez-vous vraiment vous déconnecter ? Dites oui pour confirmer ou non pour annuler.", cancelled: "Action annulée.",
    micUnsupported: "La reconnaissance vocale n’est pas prise en charge par ce navigateur.",
    micDenied: "Accès au microphone refusé. Autorisez-le dans les paramètres du navigateur.",
    micError: "La saisie vocale a échoué. Réessayez.", notificationsNone: "Vous n’avez aucune notification non lue.",
    notificationsError: "Impossible de récupérer les notifications.", speechUnsupported: "La lecture vocale n’est pas prise en charge par ce navigateur.", moduleOpened: "Ouverture du module", documentsOpened: "Espace documentaire ouvert.",
  },
  en: {
    title: "AI Assistant", placeholder: "Write your question…", clear: "Clear",
    close: "Close", send: "Send", welcome: "Hello! I can guide you through the ERP and adapt my help to the current module.",
    context: "Context", suggestions: ["Create an order", "Sales summary", "Top products", "Top customers"],
    micStart: "Start voice input", micStop: "Stop voice input",
    voiceOn: "Enable spoken replies", voiceOff: "Disable spoken replies",
    readNotifications: "Read my unread notifications", listening: "Listening…", conversationOn: "Conversation mode", conversationOff: "Stop conversation", conversationStarted: "Conversation mode on. I am listening.", conversationStopped: "Conversation mode off.", conversationEnded: "Conversation ended: no speech detected.", confirmLogout: "Do you really want to sign out? Say yes to confirm or no to cancel.", cancelled: "Action cancelled.",
    micUnsupported: "Speech recognition is not supported by this browser.",
    micDenied: "Microphone access denied. Allow it in your browser settings.",
    micError: "Voice input failed. Please try again.", notificationsNone: "You have no unread notifications.",
    notificationsError: "Could not retrieve notifications.", speechUnsupported: "Spoken playback is not supported by this browser.", moduleOpened: "Opening module", documentsOpened: "Document area opened.",
  },
  ar: {
    title: "مساعد الذكاء الاصطناعي", placeholder: "اكتب سؤالك…", clear: "مسح",
    close: "إغلاق", send: "إرسال", welcome: "مرحباً! يمكنني إرشادك داخل منصة ERP وتكييف المساعدة حسب الوحدة الحالية.",
    context: "السياق", suggestions: ["إنشاء طلب", "ملخص المبيعات", "أكثر المنتجات مبيعاً", "أفضل العملاء"],
    micStart: "بدء الإدخال الصوتي", micStop: "إيقاف الإدخال الصوتي",
    voiceOn: "تفعيل الردود الصوتية", voiceOff: "إيقاف الردود الصوتية",
    readNotifications: "قراءة إشعاراتي غير المقروءة", listening: "أنا أستمع إليك…", conversationOn: "وضع المحادثة", conversationOff: "إيقاف المحادثة", conversationStarted: "تم تفعيل وضع المحادثة. أنا أستمع إليك.", conversationStopped: "تم إيقاف وضع المحادثة.", conversationEnded: "انتهت المحادثة: لم يتم رصد أي كلام.", confirmLogout: "هل تريد فعلاً تسجيل الخروج؟ قل نعم للتأكيد أو لا للإلغاء.", cancelled: "تم إلغاء الإجراء.",
    micUnsupported: "التعرف على الكلام غير مدعوم في هذا المتصفح.",
    micDenied: "تم رفض الوصول إلى الميكروفون. يرجى السماح به من إعدادات المتصفح.",
    micError: "تعذر الإدخال الصوتي. حاول مرة أخرى.", notificationsNone: "ليس لديك إشعارات غير مقروءة.",
    notificationsError: "تعذر جلب الإشعارات.", speechUnsupported: "تشغيل الصوت غير مدعوم في هذا المتصفح.", moduleOpened: "جارٍ فتح الوحدة", documentsOpened: "تم فتح مساحة المستندات.",
  },
};

function getSpeechRecognition() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export default function AssistantIA({ open, onClose }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [langue, setLangue] = useState(() => localStorage.getItem("erp_assistant_lang") || "fr");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [state, setState] = useState({ operation: null, step: null, data: {} });
  const [docsOpen, setDocsOpen] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceListening, setVoiceListening] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const recognitionRef = useRef(null);
  const [conversation, setConversation] = useState(false);     // mode mains libres (écoute -> réponse parlée -> écoute)
  const [confirmation, setConfirmation] = useState(null);      // action sensible en attente d'un « oui » oral
  const conversationRef = useRef(false);
  const confirmationRef = useRef(null);
  const relancerMicroRef = useRef(null);
  const silencesRef = useRef(0);
  conversationRef.current = conversation;
  confirmationRef.current = confirmation;

  const module = useMemo(() => getModule(location.pathname), [location.pathname]);
  const ui = TEXTES[langue] || TEXTES.fr;
  const rtl = langue === "ar";
  const speechSupported = typeof window !== "undefined"
    && Boolean(window.speechSynthesis)
    && typeof window.SpeechSynthesisUtterance === "function";

  const parler = useCallback((texte, surFin) => {
    if (!speechSupported || !texte) { if (surFin) surFin(); return; }
    window.speechSynthesis.cancel();
    const utterance = new window.SpeechSynthesisUtterance(String(texte));
    utterance.lang = LANGUES.find((l) => l.code === langue)?.speech || "fr-FR";
    utterance.rate = 1;
    utterance.pitch = 1;
    if (surFin) { utterance.onend = surFin; utterance.onerror = surFin; }   // enchaîne l'écoute en mode conversation
    window.speechSynthesis.speak(utterance);
  }, [langue, speechSupported]);

  useEffect(() => { localStorage.setItem("erp_assistant_lang", langue); }, [langue]);

  useEffect(() => {
    if (open && messages.length === 0) setMessages([{ role: "assistant", text: ui.welcome }]);
  }, [open, langue]);

  useEffect(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setVoiceListening(false);
    setVoiceStatus("");
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
  }, [langue]);

  useEffect(() => () => {
    conversationRef.current = false;
    if (recognitionRef.current) recognitionRef.current.stop();
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
  }, []);

  const envoyerTexte = useCallback(async (texte) => {
    const question = String(texte || "").trim();
    if (!question || sending) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setSending(true);
    try {
      const res = await fetch(`${API_BASE_URL}/assistant/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({ message: question, langue, module, state }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "assistant_error");
      if (data.state) setState(data.state);
      const reply = data.reply || "";
      setMessages((m) => [...m, {
        role: "assistant", text: reply,
        sources: Array.isArray(data.sources) ? data.sources : [],
      }]);
      if (voiceEnabled && reply) parler(reply, conversationRef.current ? () => relancerMicroRef.current?.() : undefined);
      else if (conversationRef.current) relancerMicroRef.current?.();
    } catch {
      const fallback = langue === "ar"
        ? "تعذر الاتصال بالمساعد حالياً."
        : langue === "en"
          ? "The assistant could not be reached right now."
          : "Impossible de contacter l’assistant pour le moment.";
      setMessages((m) => [...m, { role: "assistant", text: fallback }]);
      if (voiceEnabled) parler(fallback);
    } finally {
      setSending(false);
    }
  }, [langue, module, state, sending, voiceEnabled, parler]);

  async function envoyer(e) {
    e?.preventDefault();
    await envoyerTexte(input);
  }

  function repondre(texte, surFin) {
    setMessages((m) => [...m, { role: "assistant", text: texte }]);
    if (voiceEnabled || conversationRef.current) parler(texte, surFin);
    else if (surFin) surFin();
  }

  async function executerDeconnexion() {
    conversationRef.current = false;
    setConversation(false);
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    await deconnecter();
    navigate("/");
  }

  // Renvoie true si la phrase était une commande (traitée ici), false si c'est une question pour l'IA.
  function traiterCommandeVocale(texte) {
    const commande = interpreter(texte, { confirmationEnAttente: Boolean(confirmationRef.current) });
    if (!commande) {
      if (confirmationRef.current) setConfirmation(null);   // phrase sans rapport : par prudence, rien n'est exécuté
      return false;
    }
    const relance = conversationRef.current ? () => relancerMicroRef.current?.() : undefined;
    switch (commande.type) {
      case "confirmer": {
        const action = confirmationRef.current;
        setConfirmation(null);
        if (action === "deconnexion") void executerDeconnexion();
        return true;
      }
      case "annuler":
        setConfirmation(null);
        repondre(ui.cancelled, relance);
        return true;
      case "navigation":
        navigate(commande.chemin);
        repondre(`${ui.moduleOpened} ${commande.nom}.`, relance);
        return true;
      case "documents":
        setDocsOpen(true);
        repondre(ui.documentsOpened, relance);
        return true;
      case "notifications":
        void lireNotifications();
        return true;
      case "deconnexion":
        // Action sensible : jamais exécutée sur la seule parole, une confirmation orale est exigée.
        setConfirmation("deconnexion");
        repondre(ui.confirmLogout, () => relancerMicroRef.current?.());
        return true;
      case "conversation":
        if (commande.actif) {
          silencesRef.current = 0;
          conversationRef.current = true;
          setConversation(true);
          setVoiceEnabled(true);
          repondre(ui.conversationStarted, () => relancerMicroRef.current?.());
        } else {
          conversationRef.current = false;
          setConversation(false);
          repondre(ui.conversationStopped);
        }
        return true;
      default:
        return false;
    }
  }

  function basculerConversation() {
    if (!getSpeechRecognition()) { setVoiceStatus(ui.micUnsupported); return; }
    if (!speechSupported) { setVoiceStatus(ui.speechUnsupported); return; }
    if (conversationRef.current) {
      conversationRef.current = false;
      setConversation(false);
      recognitionRef.current?.stop();
      window.speechSynthesis.cancel();
      return;
    }
    silencesRef.current = 0;
    conversationRef.current = true;
    setConversation(true);
    setVoiceEnabled(true);
    demarrerMicro();
  }

  function demarrerMicro() {
    const Recognition = getSpeechRecognition();
    if (!Recognition) {
      setVoiceStatus(ui.micUnsupported);
      return;
    }
    if (recognitionRef.current) recognitionRef.current.stop();

    const recognition = new Recognition();
    recognition.lang = LANGUES.find((l) => l.code === langue)?.speech || "fr-FR";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    let resultatRecu = false;
    recognition.onstart = () => {
      setVoiceListening(true);
      setVoiceStatus(ui.listening);
    };
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim();
      if (transcript) {
        resultatRecu = true;
        silencesRef.current = 0;
        setVoiceStatus("");
        if (!traiterCommandeVocale(transcript)) void envoyerTexte(transcript);
      }
    };
    recognition.onerror = (event) => {
      console.error("ERREUR RECONNAISSANCE VOCALE :", {
        error: event.error,
        message: event.message
      });

      setVoiceListening(false);
      if (event.error === "no-speech" && conversationRef.current) return;   // silence : géré dans onend
      const refuse = event.error === "not-allowed" || event.error === "service-not-allowed";
      setVoiceStatus(refuse ? ui.micDenied : `${ui.micError} (${event.error})`);
      conversationRef.current = false;
      setConversation(false);
    };
    recognition.onend = () => {
      setVoiceListening(false);
      recognitionRef.current = null;
      if (conversationRef.current && !resultatRecu) {
        silencesRef.current += 1;
        if (silencesRef.current >= 3) {            // trois silences d'affilée : on rend la main
          conversationRef.current = false;
          setConversation(false);
          setVoiceStatus(ui.conversationEnded);
        } else {
          setTimeout(() => { if (conversationRef.current) relancerMicroRef.current?.(); }, 400);
        }
      }
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      setVoiceListening(false);
      setVoiceStatus(ui.micError);
      recognitionRef.current = null;
    }
  }

  function arreterMicro() {
    recognitionRef.current?.stop();
    setVoiceListening(false);
  }

  relancerMicroRef.current = demarrerMicro;

  async function lireNotifications() {
    const token = localStorage.getItem("token");
    if (!token) {
      setVoiceStatus(ui.notificationsError);
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/notifications?limit=10&non_lues_seulement=true`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ui.notificationsError);
      const items = Array.isArray(data.notifications) ? data.notifications : [];
      if (!items.length) {
        setVoiceStatus(ui.notificationsNone);
        parler(ui.notificationsNone);
        return;
      }
      const texte = items.slice(0, 5).map((n, index) =>
        `${index + 1}. ${n.titre}. ${n.message}`
      ).join(". ");
      setMessages((m) => [...m, { role: "assistant", text: texte }]);
      setVoiceStatus("");
      parler(texte);
    } catch {
      setVoiceStatus(ui.notificationsError);
    }
  }

  function effacer() {
    setMessages([]);
    setState({ operation: null, step: null, data: {} });
    setInput("");
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
  }

  if (!open) return null;

  return (
    <section className={`assistant-panel${rtl ? " assistant-panel--rtl" : ""}`} dir={rtl ? "rtl" : "ltr"} aria-label={ui.title}>
      <header className="assistant-panel__header">
        <div className="assistant-panel__titre">
          <span className="assistant-panel__icone"><Sparkles size={16} /></span>
          <div><strong>{ui.title}</strong><small>{ui.context}: {module}</small></div>
        </div>
        <div className="assistant-panel__actions">
          <button type="button" onClick={() => setDocsOpen((v) => !v)} title="Documents" aria-label="Documents" aria-pressed={docsOpen}><Paperclip size={16} /></button>
          <button type="button" onClick={effacer} title={ui.clear} aria-label={ui.clear}><Trash2 size={16} /></button>
          <button type="button" onClick={onClose} title={ui.close} aria-label={ui.close}><X size={18} /></button>
        </div>
      </header>

      <div className="assistant-panel__langues" aria-label="Assistant language">
        {LANGUES.map((l) => <button key={l.code} type="button" className={langue === l.code ? "actif" : ""} onClick={() => setLangue(l.code)} aria-pressed={langue === l.code}>{l.label}</button>)}
      </div>

      <div className="assistant-panel__voice" aria-label="Voice controls">
        <button type="button" onClick={() => {
          if (!speechSupported) {
            setVoiceStatus(ui.speechUnsupported);
            return;
          }
          setVoiceEnabled((v) => {
            const next = !v;
            if (!next && window.speechSynthesis) window.speechSynthesis.cancel();
            return next;
          });
          setVoiceStatus("");
        }} aria-pressed={voiceEnabled} title={voiceEnabled ? ui.voiceOff : ui.voiceOn}>
          {voiceEnabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
          <span>{voiceEnabled ? ui.voiceOff : ui.voiceOn}</span>
        </button>
        <button type="button" onClick={voiceListening ? arreterMicro : demarrerMicro} disabled={sending} aria-pressed={voiceListening} title={voiceListening ? ui.micStop : ui.micStart}>
          {voiceListening ? <MicOff size={16} /> : <Mic size={16} />}
          <span>{voiceListening ? ui.micStop : ui.micStart}</span>
        </button>
        <button type="button" onClick={basculerConversation} aria-pressed={conversation} title={conversation ? ui.conversationOff : ui.conversationOn}>
          <Headphones size={16} />
          <span>{conversation ? ui.conversationOff : ui.conversationOn}</span>
        </button>
        <button type="button" onClick={lireNotifications} title={ui.readNotifications}>
          <BellRing size={16} /><span>{ui.readNotifications}</span>
        </button>
      </div>
      {voiceStatus && <p className="assistant-panel__voice-status" role="status">{voiceStatus}</p>}

      {docsOpen && <DocumentsRag langue={langue} />}
      <div className="assistant-panel__messages" aria-live="polite" aria-relevant="additions">
        {messages.map((m, i) => (
          <div key={i} className={`assistant-message assistant-message--${m.role}`}>
            <div>{m.text}</div>
            {m.role === "assistant" && m.sources?.length > 0 && (
              <div className="assistant-sources">
                <strong>{langue === "en" ? "Sources" : langue === "ar" ? "المصادر" : "Sources"}</strong>
                {m.sources.map((source, j) => (
                  <details key={`${source.id}-${j}`}>
                    <summary>[{j + 1}] {source.title} · {source.source}</summary>
                    <small>{source.module}</small><p>{source.excerpt}</p>
                  </details>
                ))}
              </div>
            )}
          </div>
        ))}
        {sending && <div className="assistant-message assistant-message--assistant">…</div>}
        {messages.length <= 1 && (
          <div className="assistant-panel__suggestions">
            {ui.suggestions.map((s) => <button key={s} type="button" onClick={() => setInput(s)}>{s}</button>)}
          </div>
        )}
      </div>

      <form className="assistant-panel__form" onSubmit={envoyer}>
        <ChampSuggestions value={input} onChange={setInput} placeholder={ui.placeholder} ariaLabel={ui.placeholder} langue={langue} module={module} />
        <button type="submit" disabled={!input.trim() || sending} title={ui.send} aria-label={ui.send}><Send size={17} /></button>
      </form>
    </section>
  );
}

