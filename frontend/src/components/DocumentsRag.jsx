import { useCallback, useEffect, useRef, useState } from "react";
import { Upload, Trash2, FileText, Loader2 } from "lucide-react";
import { API_BASE_URL } from "../api/config";

const TAILLE_MAX = 10 * 1024 * 1024;

const T = {
  fr: { titre: "Documents de l’entreprise", aide: "Importez un PDF ou DOCX (10 Mo max), puis posez vos questions à l’assistant.", choisir: "Choisir un fichier", titreDoc: "Titre (facultatif)", importer: "Importer", encours: "Importation…", vide: "Aucun document importé.", ok: "Document importé", trop: "Fichier trop volumineux (10 Mo maximum).", format: "Seuls les fichiers PDF et DOCX sont acceptés.", supprimer: "Supprimer", confirm: "Supprimer ce document ?", reseau: "Impossible de contacter le serveur.", interdit: "Vous n’avez pas la permission d’effectuer cette action.", sessionExp: "Session expirée, reconnectez-vous." },
  en: { titre: "Company documents", aide: "Upload a PDF or DOCX (10 MB max), then ask the assistant about it.", choisir: "Choose a file", titreDoc: "Title (optional)", importer: "Upload", encours: "Uploading…", vide: "No documents imported.", ok: "Document imported", trop: "File too large (10 MB maximum).", format: "Only PDF and DOCX files are accepted.", supprimer: "Delete", confirm: "Delete this document?", reseau: "Cannot reach the server.", interdit: "You do not have permission to do this.", sessionExp: "Session expired, please sign in again." },
  ar: { titre: "وثائق الشركة", aide: "استورد ملف PDF أو DOCX (10 ميغابايت كحد أقصى) ثم اطرح أسئلتك على المساعد.", choisir: "اختر ملفاً", titreDoc: "العنوان (اختياري)", importer: "استيراد", encours: "جارٍ الاستيراد…", vide: "لا توجد وثائق.", ok: "تم استيراد الوثيقة", trop: "الملف كبير جداً (10 ميغابايت كحد أقصى).", format: "يُقبل فقط PDF و DOCX.", supprimer: "حذف", confirm: "حذف هذه الوثيقة؟", reseau: "تعذر الاتصال بالخادم.", interdit: "ليست لديك صلاحية لهذه العملية.", sessionExp: "انتهت الجلسة، أعد تسجيل الدخول." },
};

function entetes() {
  // Même mécanisme que le reste de l'ERP : jeton JWT du localStorage en Bearer.
  return { Authorization: `Bearer ${localStorage.getItem("token")}` };
}

export default function DocumentsRag({ langue = "fr" }) {
  const t = T[langue] || T.fr;
  const [docs, setDocs] = useState([]);
  const [fichier, setFichier] = useState(null);
  const [titre, setTitre] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null); // { type: "ok" | "err", text }
  const inputRef = useRef(null);

  const messageErreur = useCallback((res, data) => {
    if (res.status === 401) return t.sessionExp;
    if (res.status === 403) return t.interdit;
    // 413/422 : le backend renvoie déjà un message lisible, sans détail technique.
    return typeof data?.detail === "string" ? data.detail : t.reseau;
  }, [t]);

  const charger = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/assistant/documents`, { headers: entetes() });
      const data = await res.json().catch(() => null);
      if (res.ok) setDocs(Array.isArray(data) ? data : []);
      else if (res.status !== 403) setMsg({ type: "err", text: messageErreur(res, data) });
    } catch { setMsg({ type: "err", text: t.reseau }); }
  }, [messageErreur, t]);

  useEffect(() => { charger(); }, [charger]);

  function choisir(e) {
    const f = e.target.files?.[0] || null;
    setMsg(null);
    if (f && !/\.(pdf|docx)$/i.test(f.name)) { setMsg({ type: "err", text: t.format }); setFichier(null); return; }
    if (f && f.size > TAILLE_MAX) { setMsg({ type: "err", text: t.trop }); setFichier(null); return; }
    setFichier(f);
  }

  async function importer(e) {
    e.preventDefault();
    if (!fichier || busy) return;
    setBusy(true); setMsg(null);
    const form = new FormData(); // pas de Content-Type manuel : le navigateur ajoute le boundary
    form.append("fichier", fichier);
    if (titre.trim()) form.append("titre", titre.trim());
    form.append("langue", langue);
    try {
      const res = await fetch(`${API_BASE_URL}/assistant/documents/upload`, { method: "POST", headers: entetes(), body: form });
      const data = await res.json().catch(() => null);
      if (!res.ok) { setMsg({ type: "err", text: messageErreur(res, data) }); return; }
      setMsg({ type: "ok", text: `${t.ok} : ${data.titre} (${data.nbChunks})` });
      setFichier(null); setTitre(""); if (inputRef.current) inputRef.current.value = "";
      charger();
    } catch { setMsg({ type: "err", text: t.reseau }); }
    finally { setBusy(false); }
  }

  async function supprimer(id) {
    if (!window.confirm(t.confirm)) return;
    try {
      const res = await fetch(`${API_BASE_URL}/assistant/documents/${id}`, { method: "DELETE", headers: entetes() });
      if (res.ok) charger();
      else setMsg({ type: "err", text: messageErreur(res, await res.json().catch(() => null)) });
    } catch { setMsg({ type: "err", text: t.reseau }); }
  }

  return (
    <div className="assistant-docs">
      <strong>{t.titre}</strong>
      <small>{t.aide}</small>
      <form onSubmit={importer} className="assistant-docs__form">
        <input ref={inputRef} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={choisir} aria-label={t.choisir} />
        <input type="text" value={titre} maxLength={200} onChange={(e) => setTitre(e.target.value)} placeholder={t.titreDoc} aria-label={t.titreDoc} />
        <button type="submit" disabled={!fichier || busy}>{busy ? <Loader2 size={15} className="assistant-docs__spin" /> : <Upload size={15} />} {busy ? t.encours : t.importer}</button>
      </form>
      {msg && <p className={`assistant-docs__msg assistant-docs__msg--${msg.type}`} role={msg.type === "err" ? "alert" : "status"}>{msg.text}</p>}
      <ul className="assistant-docs__liste">
        {docs.length === 0 && <li className="assistant-docs__vide">{t.vide}</li>}
        {docs.map((d) => (
          <li key={d.id}>
            <FileText size={14} />
            <span title={d.nomFichier}>{d.titre}<small> · {d.type.toUpperCase()} · {Math.max(1, Math.round(d.tailleOctets / 1024))} Ko</small></span>
            <button type="button" onClick={() => supprimer(d.id)} title={t.supprimer} aria-label={t.supprimer}><Trash2 size={14} /></button>
          </li>
        ))}
      </ul>
    </div>
  );
}
