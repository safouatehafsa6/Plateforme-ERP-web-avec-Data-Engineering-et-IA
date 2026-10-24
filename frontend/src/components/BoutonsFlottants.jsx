import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, ChevronDown, Headset, MessageCircle, LogIn, UserPlus, X, Bell, CheckCheck, ArrowLeft, LoaderCircle } from "lucide-react";
import { lireSession } from "../api/session";
import { API_BASE_URL } from "../api/config";
import { useLangue } from "../context/LangueContext";
import AssistantIA from "./AssistantIA";

const TEXTES = {
  fr: { menu: "Ouvrir le menu d’assistance", close: "Fermer le menu", title: "Besoin d’aide ?", assistant: "Assistant IA", support: "Assistance / Contact", whatsapp: "WhatsApp", login: "Connexion", signup: "Créer un compte", unavailable: "Contact non configuré", notifications: "Notifications", markAll: "Tout marquer comme lu", empty: "Aucune notification pour le moment.", loading: "Chargement…", loadError: "Impossible de charger les notifications.", back: "Retour", markRead: "Marquer comme lue", unread: "non lues" },
  en: { menu: "Open help menu", close: "Close help menu", title: "How can we help?", assistant: "AI Assistant", support: "Support / Contact", whatsapp: "WhatsApp", login: "Sign in", signup: "Create account", unavailable: "Contact is not configured", notifications: "Notifications", markAll: "Mark all as read", empty: "No notifications yet.", loading: "Loading…", loadError: "Could not load notifications.", back: "Back", markRead: "Mark as read", unread: "unread" },
  ar: { menu: "فتح قائمة المساعدة", close: "إغلاق قائمة المساعدة", title: "كيف يمكننا مساعدتك؟", assistant: "مساعد الذكاء الاصطناعي", support: "الدعم / التواصل", whatsapp: "واتساب", login: "تسجيل الدخول", signup: "إنشاء حساب", unavailable: "بيانات التواصل غير مهيأة", notifications: "الإشعارات", markAll: "تحديد الكل كمقروء", empty: "لا توجد إشعارات حالياً.", loading: "جارٍ التحميل…", loadError: "تعذر تحميل الإشعارات.", back: "رجوع", markRead: "تحديد كمقروء", unread: "غير مقروءة" },
};

const PUBLIC_ROUTES = new Set(["/", "/inscription", "/mot-de-passe-oublie", "/fonctionnalites", "/tarifs"]);

export default function BoutonsFlottants() {
  const { i18n } = useTranslation();
  const { langueActuelle } = useLangue();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOuvert, setMenuOuvert] = useState(false);
  const [notificationsOuvertes, setNotificationsOuvertes] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [notificationsNonLues, setNotificationsNonLues] = useState(0);
  const [chargementNotifications, setChargementNotifications] = useState(false);
  const [erreurNotifications, setErreurNotifications] = useState("");
  const [assistantOuvert, setAssistantOuvert] = useState(false);
  const session = useMemo(() => lireSession(), [location.pathname]);
  const langue = (langueActuelle?.code || i18n.language || "fr").split("-")[0];
  const rtl = langue === "ar";
  const ui = TEXTES[langue] || TEXTES.fr;
  const estPublic = PUBLIC_ROUTES.has(location.pathname) || location.pathname.startsWith("/verifier/");
  const whatsappNumber = (import.meta.env.VITE_WHATSAPP_NUMBER || "").replace(/\D/g, "");
  const supportEmail = import.meta.env.VITE_SUPPORT_EMAIL || "";

  useEffect(() => {
    setMenuOuvert(false);
    setAssistantOuvert(false);
    setNotificationsOuvertes(false);
    if (estPublic || !session) return;

    void chargerNotifications();
    const actualiser = () => { void chargerNotifications(); };
    window.addEventListener("erp:notifications-refresh", actualiser);
    const actualiserAuRetour = () => {
      if (document.visibilityState === "visible") actualiser();
    };
    window.addEventListener("focus", actualiser);
    document.addEventListener("visibilitychange", actualiserAuRetour);
    // Rafraîchissement régulier : une notification créée ailleurs (autre onglet, autre
    // utilisateur, tâche automatique) apparaît sans recharger la page.
    const minuteur = window.setInterval(() => {
      if (document.visibilityState === "visible") actualiser();
    }, 30000);
    return () => {
      window.clearInterval(minuteur);
      window.removeEventListener("erp:notifications-refresh", actualiser);
      window.removeEventListener("focus", actualiser);
      document.removeEventListener("visibilitychange", actualiserAuRetour);
    };
  }, [location.pathname, langue, estPublic, Boolean(session)]);

  async function chargerNotifications() {
    const token = localStorage.getItem("token");
    if (!token) return;
    setChargementNotifications(true);
    setErreurNotifications("");
    try {
      const res = await fetch(`${API_BASE_URL}/notifications?limit=30`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ui.loadError);
      setNotifications(Array.isArray(data.notifications) ? data.notifications : []);
      setNotificationsNonLues(Number(data.nonLues || 0));
    } catch (e) {
      setErreurNotifications(e.message || ui.loadError);
    } finally {
      setChargementNotifications(false);
    }
  }

  async function ouvrirNotifications() {
    setNotificationsOuvertes(true);
    await chargerNotifications();
  }

  async function marquerLue(notification) {
    const token = localStorage.getItem("token");
    if (!token || notification.lue) return;
    try {
      const res = await fetch(`${API_BASE_URL}/notifications/${notification.id}/lue`, {
        method: "PATCH", headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ui.loadError);
      setNotifications((prev) => prev.map((n) => n.id === notification.id ? { ...n, lue: true } : n));
      setNotificationsNonLues((prev) => Math.max(0, prev - 1));
    } catch (e) {
      setErreurNotifications(e.message || ui.loadError);
    }
  }

  async function marquerToutesLues() {
    const token = localStorage.getItem("token");
    if (!token || notificationsNonLues === 0) return;
    try {
      const res = await fetch(`${API_BASE_URL}/notifications/lire-toutes`, {
        method: "PATCH", headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ui.loadError);
      setNotifications((prev) => prev.map((n) => ({ ...n, lue: true })));
      setNotificationsNonLues(0);
    } catch (e) {
      setErreurNotifications(e.message || ui.loadError);
    }
  }

  function ouvrirLienNotification(notification) {
    if (!notification.lue) void marquerLue(notification);
    if (notification.lien) {
      setMenuOuvert(false);
      setNotificationsOuvertes(false);
      navigate(notification.lien);
    }
  }


  function ouvrirAssistant() {
    setMenuOuvert(false);
    setAssistantOuvert(true);
  }

  return (
    <div className={`boutons-flottants${rtl ? " boutons-flottants--rtl" : ""}`} dir={rtl ? "rtl" : "ltr"}>
      {menuOuvert && (
        <section className="boutons-flottants__menu" aria-label={notificationsOuvertes ? ui.notifications : ui.title}>
          <div className="boutons-flottants__menu-titre">
            {notificationsOuvertes ? <button type="button" onClick={() => setNotificationsOuvertes(false)} aria-label={ui.back}><ArrowLeft size={17} /></button> : null}
            <span>{notificationsOuvertes ? ui.notifications : ui.title}</span>
            <button type="button" onClick={() => { setMenuOuvert(false); setNotificationsOuvertes(false); }} aria-label={ui.close}><X size={17} /></button>
          </div>
          {notificationsOuvertes ? (
            <div className="boutons-flottants__notifications">
              {notificationsNonLues > 0 && <button type="button" className="boutons-flottants__tout-lire" onClick={marquerToutesLues}><CheckCheck size={15} />{ui.markAll}</button>}
              {chargementNotifications ? <p className="boutons-flottants__note"><LoaderCircle className="boutons-flottants__spinner" size={16} /> {ui.loading}</p> : null}
              {erreurNotifications ? <p className="boutons-flottants__erreur" role="alert">{erreurNotifications}</p> : null}
              {!chargementNotifications && !erreurNotifications && notifications.length === 0 ? <p className="boutons-flottants__note">{ui.empty}</p> : null}
              {notifications.map((n) => (
                <article key={n.id} className={`boutons-flottants__notification${n.lue ? " est-lue" : " est-non-lue"}`}>
                  <button type="button" className="boutons-flottants__notification-contenu" onClick={() => ouvrirLienNotification(n)}>
                    <span className={`boutons-flottants__notification-point categorie-${n.categorie || "info"}`} />
                    <span className="boutons-flottants__notification-texte"><strong>{n.titre}</strong><span>{n.message}</span><small>{n.creeLe ? new Date(n.creeLe).toLocaleString(langue === "ar" ? "ar" : langue === "en" ? "en" : "fr") : ""}</small></span>
                  </button>
                  {!n.lue && <button type="button" className="boutons-flottants__notification-lire" onClick={() => marquerLue(n)} aria-label={ui.markRead} title={ui.markRead}><CheckCheck size={15} /></button>}
                </article>
              ))}
            </div>
          ) : <>
          {!estPublic && session && (
            <button type="button" className="boutons-flottants__item" onClick={ouvrirNotifications}>
              <Bell size={19} /><span>{ui.notifications}</span>
              {notificationsNonLues > 0 && <span className="boutons-flottants__badge">{notificationsNonLues > 99 ? "99+" : notificationsNonLues}</span>}
            </button>
          )}
          {!estPublic && session && (
            <button type="button" className="boutons-flottants__item" onClick={ouvrirAssistant}>
              <Bot size={19} /><span>{ui.assistant}</span>
            </button>
          )}
          {whatsappNumber && (
            <a className="boutons-flottants__item" href={`https://wa.me/${whatsappNumber}`} target="_blank" rel="noopener noreferrer">
              <MessageCircle size={19} /><span>{ui.whatsapp}</span>
            </a>
          )}
          {supportEmail && (
            <a className="boutons-flottants__item" href={`mailto:${supportEmail}?subject=${encodeURIComponent("Support BENJEDDOU ERP")}`}>
              <Headset size={19} /><span>{ui.support}</span>
            </a>
          )}
          {estPublic && <>
            <Link className="boutons-flottants__item" to="/" onClick={() => setMenuOuvert(false)}><LogIn size={19} /><span>{ui.login}</span></Link>
            <Link className="boutons-flottants__item" to="/inscription" onClick={() => setMenuOuvert(false)}><UserPlus size={19} /><span>{ui.signup}</span></Link>
          </>}
          {!session && !estPublic && <Link className="boutons-flottants__item" to="/" onClick={() => setMenuOuvert(false)}><LogIn size={19} /><span>{ui.login}</span></Link>}
          {!whatsappNumber && !supportEmail && (estPublic || session) && (
            <p className="boutons-flottants__note">{ui.unavailable}</p>
          )}
          </>}
        </section>
      )}

      <button
        type="button"
        className={`boutons-flottants__principal${menuOuvert ? " est-ouvert" : ""}`}
        onClick={() => setMenuOuvert((ouvert) => !ouvert)}
        aria-label={menuOuvert ? ui.close : ui.menu}
        aria-expanded={menuOuvert}
        title={menuOuvert ? ui.close : ui.menu}
      >
        {menuOuvert ? <X size={23} /> : <Headset size={23} />}
        {!menuOuvert && notificationsNonLues > 0 && session && <span className="boutons-flottants__principal-badge">{notificationsNonLues > 99 ? "99+" : notificationsNonLues}</span>}
        <span className="boutons-flottants__chevron"><ChevronDown size={14} /></span>
      </button>

      {assistantOuvert && <AssistantIA open={assistantOuvert} onClose={() => setAssistantOuvert(false)} />}
    </div>
  );
}
