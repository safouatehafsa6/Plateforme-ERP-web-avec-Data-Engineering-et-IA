import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Headset, Send, Paperclip, X, Image as ImageIcon, LoaderCircle } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";
import { useLangue } from "../context/LangueContext";
import { lireSession, estAdminEntreprise, estUtilisateurExterne } from "../api/session";

const TEXTES = {
  fr: {
    titre: "Assistance / Contact", intro: "Signalez un problème ou posez une question. Vous pouvez joindre une capture d’écran et suivre l’avancement de votre demande.",
    nouvelle: "Nouvelle demande", sujet: "Sujet", sujetPh: "Ex. : le PDF de la facture ne s’ouvre pas", description: "Description", descriptionPh: "Décrivez ce qui s’est passé et ce que vous attendiez.",
    capture: "Joindre une capture d’écran", retirer: "Retirer la capture", envoyer: "Envoyer la demande", envoi: "Envoi…", envoye: "Votre demande a bien été envoyée.",
    mes: "Mes demandes", toutes: "Toutes les demandes", aucune: "Aucune demande pour le moment.", chargement: "Chargement…", voirCapture: "Voir la capture",
    statuts: { ouverte: "Ouverte", en_cours: "En cours", resolue: "Résolue" }, statut: "Statut", page: "Page concernée", auteur: "Auteur",
    imageInvalide: "Choisissez une image PNG, JPEG ou WebP.", imageTrop: "L’image dépasse 2 Mo.", erreur: "Une erreur est survenue.",
  },
  en: {
    titre: "Support / Contact", intro: "Report a problem or ask a question. You can attach a screenshot and follow the progress of your request.",
    nouvelle: "New request", sujet: "Subject", sujetPh: "E.g. the invoice PDF does not open", description: "Description", descriptionPh: "Describe what happened and what you expected.",
    capture: "Attach a screenshot", retirer: "Remove screenshot", envoyer: "Send request", envoi: "Sending…", envoye: "Your request has been sent.",
    mes: "My requests", toutes: "All requests", aucune: "No requests yet.", chargement: "Loading…", voirCapture: "View screenshot",
    statuts: { ouverte: "Open", en_cours: "In progress", resolue: "Resolved" }, statut: "Status", page: "Related page", auteur: "Author",
    imageInvalide: "Choose a PNG, JPEG or WebP image.", imageTrop: "The image is larger than 2 MB.", erreur: "Something went wrong.",
  },
  ar: {
    titre: "الدعم / التواصل", intro: "أبلغ عن مشكلة أو اطرح سؤالاً. يمكنك إرفاق لقطة شاشة ومتابعة تقدم طلبك.",
    nouvelle: "طلب جديد", sujet: "الموضوع", sujetPh: "مثال: ملف PDF للفاتورة لا يفتح", description: "الوصف", descriptionPh: "صف ما حدث وما كنت تتوقعه.",
    capture: "إرفاق لقطة شاشة", retirer: "إزالة اللقطة", envoyer: "إرسال الطلب", envoi: "جارٍ الإرسال…", envoye: "تم إرسال طلبك بنجاح.",
    mes: "طلباتي", toutes: "جميع الطلبات", aucune: "لا توجد طلبات حالياً.", chargement: "جارٍ التحميل…", voirCapture: "عرض اللقطة",
    statuts: { ouverte: "مفتوح", en_cours: "قيد المعالجة", resolue: "تم الحل" }, statut: "الحالة", page: "الصفحة المعنية", auteur: "الكاتب",
    imageInvalide: "اختر صورة PNG أو JPEG أو WebP.", imageTrop: "حجم الصورة يتجاوز 2 ميغابايت.", erreur: "حدث خطأ.",
  },
};

async function api(endpoint, options = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail || data?.message || `Erreur ${res.status}`);
  return data;
}

const lireFichier = (fichier) => new Promise((resolve, reject) => {
  const lecteur = new FileReader();
  lecteur.onload = () => resolve(lecteur.result);
  lecteur.onerror = reject;
  lecteur.readAsDataURL(fichier);
});

export default function Support() {
  const { langueActuelle } = useLangue();
  const location = useLocation();
  const langue = langueActuelle?.code || "fr";
  const t = TEXTES[langue] || TEXTES.fr;
  const session = useMemo(() => lireSession(), []);
  const admin = estAdminEntreprise(session);
  const externe = estUtilisateurExterne(session);
  const [onglet, setOnglet] = useState("mes");
  const [demandes, setDemandes] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [succes, setSucces] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [form, setForm] = useState({ sujet: "", description: "" });
  const [capture, setCapture] = useState(null);
  const champFichier = useRef(null);

  async function charger(cible = onglet) {
    setChargement(true);
    try {
      const r = await api(cible === "toutes" ? "/support/admin/demandes" : "/support/demandes");
      setDemandes(r.demandes || []);
    } catch (e) { setErreur(e.message); } finally { setChargement(false); }
  }
  useEffect(() => { charger(onglet); }, [onglet]);

  async function choisirImage(e) {
    const fichier = e.target.files?.[0];
    e.target.value = "";
    if (!fichier) return;
    setErreur("");
    if (!["image/png", "image/jpeg", "image/webp"].includes(fichier.type)) { setErreur(t.imageInvalide); return; }
    if (fichier.size > 2 * 1024 * 1024) { setErreur(t.imageTrop); return; }
    setCapture({ nom: fichier.name, url: await lireFichier(fichier) });
  }

  async function envoyer(e) {
    e.preventDefault();
    setEnvoi(true); setErreur(""); setSucces("");
    try {
      await api("/support/demandes", {
        method: "POST",
        body: JSON.stringify({ sujet: form.sujet, description: form.description, page: location.state?.from || null, capture: capture?.url || null }),
      });
      setForm({ sujet: "", description: "" }); setCapture(null); setSucces(t.envoye);
      window.dispatchEvent(new Event("erp:notifications-refresh"));
      setOnglet("mes"); await charger("mes");
    } catch (err) { setErreur(err.message || t.erreur); } finally { setEnvoi(false); }
  }

  async function voirCapture(id) {
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_BASE_URL}/support/demandes/${id}/capture`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(t.erreur);
      window.open(URL.createObjectURL(await res.blob()), "_blank", "noopener");
    } catch (err) { setErreur(err.message); }
  }

  async function changerStatut(id, statut) {
    try {
      await api(`/support/admin/demandes/${id}`, { method: "PATCH", body: JSON.stringify({ statut }) });
      setDemandes((liste) => liste.map((d) => (d.id === id ? { ...d, statut } : d)));
    } catch (err) { setErreur(err.message); }
  }

  const contenu = (
    <main className="app-main support-page" dir={langue === "ar" ? "rtl" : "ltr"}>
      <h1 className="app-main__titre"><Headset size={26} /> {t.titre}</h1>
      <p className="support-intro">{t.intro}</p>
      {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
      {succes && <div className="support-succes" role="status">{succes}</div>}

      <form className="panel support-form" onSubmit={envoyer}>
        <h2>{t.nouvelle}</h2>
        <div className="champ"><label htmlFor="support-sujet">{t.sujet}</label>
          <input id="support-sujet" value={form.sujet} onChange={(e) => setForm({ ...form, sujet: e.target.value })} placeholder={t.sujetPh} required minLength={3} maxLength={150} /></div>
        <div className="champ"><label htmlFor="support-description">{t.description}</label>
          <textarea id="support-description" rows="5" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder={t.descriptionPh} required minLength={5} maxLength={4000} /></div>
        <div className="support-form__actions">
          <input ref={champFichier} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={choisirImage} />
          <button type="button" className="bouton-secondaire-large support-btn" onClick={() => champFichier.current?.click()}><Paperclip size={16} /> {t.capture}</button>
          <button className="bouton-principal support-btn" disabled={envoi}>{envoi ? <><LoaderCircle size={16} className="boutons-flottants__spinner" /> {t.envoi}</> : <><Send size={16} /> {t.envoyer}</>}</button>
        </div>
        {capture && (
          <div className="support-apercu">
            <img src={capture.url} alt={capture.nom} />
            <span>{capture.nom}</span>
            <button type="button" onClick={() => setCapture(null)} aria-label={t.retirer} title={t.retirer}><X size={16} /></button>
          </div>
        )}
      </form>

      <div className="support-onglets" role="tablist">
        <button type="button" role="tab" aria-selected={onglet === "mes"} onClick={() => setOnglet("mes")}>{t.mes}</button>
        {admin && <button type="button" role="tab" aria-selected={onglet === "toutes"} onClick={() => setOnglet("toutes")}>{t.toutes}</button>}
      </div>
      {chargement ? <p>{t.chargement}</p> : demandes.length === 0 ? <p className="support-vide">{t.aucune}</p> : (
        <div className="support-liste">
          {demandes.map((d) => (
            <article key={d.id} className="panel support-demande">
              <header>
                <strong>#{d.id} · {d.sujet}</strong>
                {onglet === "toutes" ? (
                  <select value={d.statut} onChange={(e) => changerStatut(d.id, e.target.value)} aria-label={t.statut}>
                    {Object.entries(t.statuts).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
                  </select>
                ) : <span className={`support-statut support-statut--${d.statut}`}>{t.statuts[d.statut]}</span>}
              </header>
              <p>{d.description}</p>
              <footer>
                <small>{d.creeLe ? new Date(d.creeLe).toLocaleString(langue) : ""}{d.page ? ` · ${t.page} : ${d.page}` : ""}{onglet === "toutes" && d.auteur ? ` · ${t.auteur} : ${d.auteur}` : ""}</small>
                {d.aCapture && <button type="button" className="support-lien" onClick={() => voirCapture(d.id)}><ImageIcon size={14} /> {t.voirCapture}</button>}
              </footer>
            </article>
          ))}
        </div>
      )}
    </main>
  );

  if (externe) return <div className="app-contenu support-externe">{contenu}</div>;
  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">{contenu}</div>
    </div>
  );
}
