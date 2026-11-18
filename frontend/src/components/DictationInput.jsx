import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, SpellCheck, WandSparkles, Check, X, LoaderCircle } from "lucide-react";
import { ameliorerTexte } from "../api/assistantApi";
import "./dictation-input.css";

const LANGUES = { fr: "fr-FR", en: "en-US", ar: "ar-MA" };

export default function DictationInput({ value, onChange, disabled = false, multiline = false, placeholder = "" }) {
  const [ecoute, setEcoute] = useState(false);
  const [langue, setLangue] = useState(() => localStorage.getItem("erp_assistant_lang") || "fr");
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState("");
  const [proposition, setProposition] = useState("");
  const recognitionRef = useRef(null);

  useEffect(() => () => recognitionRef.current?.stop(), []);

  function dicter() {
    const Recognition = typeof window !== "undefined"
      ? window.SpeechRecognition || window.webkitSpeechRecognition
      : null;
    if (!Recognition) {
      setErreur("La dictée vocale n'est pas prise en charge par ce navigateur. Essayez Chrome ou Edge.");
      return;
    }
    if (ecoute) {
      recognitionRef.current?.stop();
      setEcoute(false);
      return;
    }
    setErreur("");
    const recognition = new Recognition();
    recognition.lang = LANGUES[langue] || "fr-FR";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setEcoute(true);
    recognition.onresult = (event) => {
      const texte = event.results?.[0]?.[0]?.transcript?.trim();
      if (texte) onChange([String(value || "").trim(), texte].filter(Boolean).join(" "));
    };
    recognition.onerror = (event) => {
      setErreur(event.error === "not-allowed"
        ? "Autorisez l'accès au microphone dans les paramètres du navigateur."
        : `La dictée a échoué (${event.error || "erreur"}).`);
    };
    recognition.onend = () => {
      setEcoute(false);
      recognitionRef.current = null;
    };
    recognitionRef.current = recognition;
    try { recognition.start(); }
    catch { setEcoute(false); setErreur("Impossible de démarrer le microphone."); recognitionRef.current = null; }
  }

  async function proposer(mode) {
    if (!String(value || "").trim()) {
      setErreur("Saisissez ou dictez d'abord un texte.");
      return;
    }
    setChargement(true);
    setErreur("");
    try {
      setProposition(await ameliorerTexte(String(value), mode, langue));
    } catch (e) {
      setErreur(e.message || "Le service de rédaction IA est indisponible.");
    } finally { setChargement(false); }
  }

  return (
    <div className="dictation-field">
      <div className="dictation-field__control">
        {multiline
          ? <textarea value={value ?? ""} disabled={disabled} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
          : <input value={value ?? ""} disabled={disabled} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}
        <div className="dictation-field__tools">
          <select value={langue} disabled={disabled || ecoute || chargement} onChange={(e) => { setLangue(e.target.value); localStorage.setItem("erp_assistant_lang", e.target.value); }} aria-label="Langue de dictée">
            <option value="fr">FR</option><option value="ar">AR</option><option value="en">EN</option>
          </select>
          <button type="button" disabled={disabled || chargement} onClick={dicter} aria-label={ecoute ? "Arrêter la dictée" : "Dicter dans ce champ"} title={ecoute ? "Arrêter la dictée" : "Dicter"}>
            {ecoute ? <MicOff size={15} /> : <Mic size={15} />}
          </button>
          <button type="button" disabled={disabled || chargement || !String(value || "").trim()} onClick={() => proposer("correction")} aria-label="Corriger le texte" title="Corriger l'orthographe">
            <SpellCheck size={15} />
          </button>
          <button type="button" disabled={disabled || chargement || !String(value || "").trim()} onClick={() => proposer("reformulation")} aria-label="Reformuler le texte" title="Reformuler le texte">
            {chargement ? <LoaderCircle size={15} className="dictation-spin" /> : <WandSparkles size={15} />}
          </button>
        </div>
      </div>
      {erreur && <small className="dictation-field__error" role="status">{erreur}</small>}
      {proposition && (
        <div className="dictation-field__suggestion">
          <strong>Proposition IA — vérifiez avant application</strong>
          <p>{proposition}</p>
          <div>
            <button type="button" onClick={() => { onChange(proposition); setProposition(""); }}><Check size={14} /> Appliquer</button>
            <button type="button" onClick={() => setProposition("")}><X size={14} /> Ignorer</button>
          </div>
        </div>
      )}
    </div>
  );
}
