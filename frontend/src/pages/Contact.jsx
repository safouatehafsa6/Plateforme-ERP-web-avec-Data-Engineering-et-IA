import { useState } from "react";
import { MessageCircle, Send, LoaderCircle, Mail } from "lucide-react";
import FondAnime from "../components/FondAnime";
import { API_BASE_URL } from "../api/config";
import { useLangue } from "../context/LangueContext";

const TEXTES = {
  fr: { titre: "Contactez-nous", intro: "Une question sur la plateforme, les tarifs ou une démonstration ? Laissez-nous un message, nous vous répondrons rapidement.",
    nom: "Votre nom", email: "Votre e-mail", message: "Votre message", envoyer: "Envoyer le message", envoi: "Envoi…", merci: "Merci ! Votre message a bien été envoyé.", whatsapp: "Écrire sur WhatsApp", erreur: "Une erreur est survenue." },
  en: { titre: "Contact us", intro: "A question about the platform, pricing or a demo? Leave us a message and we will get back to you quickly.",
    nom: "Your name", email: "Your email", message: "Your message", envoyer: "Send message", envoi: "Sending…", merci: "Thank you! Your message has been sent.", whatsapp: "Write on WhatsApp", erreur: "Something went wrong." },
  ar: { titre: "تواصل معنا", intro: "لديك سؤال عن المنصة أو الأسعار أو تريد عرضاً تجريبياً؟ اترك لنا رسالة وسنرد عليك بسرعة.",
    nom: "اسمك", email: "بريدك الإلكتروني", message: "رسالتك", envoyer: "إرسال الرسالة", envoi: "جارٍ الإرسال…", merci: "شكراً! تم إرسال رسالتك.", whatsapp: "راسلنا على واتساب", erreur: "حدث خطأ." },
};

// Page publique : formulaire de contact pour les visiteurs (aucune connexion requise).
export default function Contact() {
  const { langueActuelle } = useLangue();
  const langue = langueActuelle?.code || "fr";
  const t = TEXTES[langue] || TEXTES.fr;
  const [form, setForm] = useState({ nom: "", email: "", message: "" });
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState("");
  const [succes, setSucces] = useState(false);
  const whatsapp = (import.meta.env.VITE_WHATSAPP_NUMBER || "").replace(/\D/g, "");

  async function envoyer(e) {
    e.preventDefault();
    setEnvoi(true); setErreur(""); setSucces(false);
    try {
      const res = await fetch(`${API_BASE_URL}/public/contact`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : t.erreur);
      setForm({ nom: "", email: "", message: "" }); setSucces(true);
    } catch (err) { setErreur(err.message || t.erreur); } finally { setEnvoi(false); }
  }

  return (
    <div className="vitrine-page" dir={langue === "ar" ? "rtl" : "ltr"}>
      <FondAnime />
      <main className="vitrine contact-page">
        <h1 className="vitrine__titre vitrine__titre--anime">{t.titre}</h1>
        <p className="vitrine__intro vitrine__intro--anime">{t.intro}</p>
        <form className="panel support-form contact-form" onSubmit={envoyer}>
          {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
          {succes && <div className="support-succes" role="status">{t.merci}</div>}
          <div className="champ"><label htmlFor="contact-nom">{t.nom}</label>
            <input id="contact-nom" value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} required minLength={2} maxLength={150} autoComplete="name" /></div>
          <div className="champ"><label htmlFor="contact-email">{t.email}</label>
            <input id="contact-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required maxLength={200} autoComplete="email" /></div>
          <div className="champ"><label htmlFor="contact-message">{t.message}</label>
            <textarea id="contact-message" rows="5" value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} required minLength={5} maxLength={3000} /></div>
          <div className="support-form__actions">
            <button className="bouton-principal support-btn" disabled={envoi}>{envoi ? <><LoaderCircle size={16} className="boutons-flottants__spinner" /> {t.envoi}</> : <><Send size={16} /> {t.envoyer}</>}</button>
            {whatsapp && <a className="bouton-secondaire-large support-btn" href={`https://wa.me/${whatsapp}`} target="_blank" rel="noopener noreferrer"><MessageCircle size={16} /> {t.whatsapp}</a>}
          </div>
        </form>
      </main>
    </div>
  );
}
