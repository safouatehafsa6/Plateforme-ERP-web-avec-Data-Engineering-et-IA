import i18n from "i18next";
import { initReactI18next } from "react-i18next";

// Langues supportées, conformément au cahier des charges (FR + EN + AR / RTL).
export const LANGUES = [
  { code: "fr", nom: "Français", dir: "ltr" },
  { code: "en", nom: "English", dir: "ltr" },
  { code: "ar", nom: "العربية", dir: "rtl" },
];

const resources = {
  fr: {
    translation: {
      connexion_titre: "Connexion",
      connexion_soustitre: "Accédez à votre espace de gestion",
      email: "Adresse e-mail",
      mot_de_passe: "Mot de passe",
      se_connecter: "Se connecter",
      mot_de_passe_oublie: "Mot de passe oublié ?",
      erreur_identifiants: "Adresse e-mail ou mot de passe incorrect.",
      marque_titre: "Une plateforme, toute votre entreprise",
      marque_texte: "Ventes, achats, stock et facturation réunis dans un seul espace, pour chacune de vos équipes.",
      tableau_de_bord: "Tableau de bord",
      ventes: "Ventes",
      achats: "Achats",
      stock: "Stock",
      clients: "Clients",
      facturation: "Facturation",
      comptabilite: "Comptabilité",
      parametres: "Paramètres",
      deconnexion: "Déconnexion",
      rechercher: "Rechercher...",
      chiffre_affaires: "Chiffre d'affaires",
      tresorerie: "Trésorerie",
      clients_actifs: "Clients actifs",
      graphiques_a_venir: "Les graphiques d'évolution et les tableaux détaillés seront ajoutés une fois le backend connecté.",
    },
  },
  en: {
    translation: {
      connexion_titre: "Sign in",
      connexion_soustitre: "Access your workspace",
      email: "Email address",
      mot_de_passe: "Password",
      se_connecter: "Sign in",
      mot_de_passe_oublie: "Forgot your password?",
      erreur_identifiants: "Incorrect email or password.",
      marque_titre: "One platform, your whole business",
      marque_texte: "Sales, purchasing, stock and invoicing brought together for every team.",
      tableau_de_bord: "Dashboard",
      ventes: "Sales",
      achats: "Purchasing",
      stock: "Stock",
      clients: "Customers",
      facturation: "Invoicing",
      comptabilite: "Accounting",
      parametres: "Settings",
      deconnexion: "Log out",
      rechercher: "Search...",
      chiffre_affaires: "Revenue",
      tresorerie: "Cash flow",
      clients_actifs: "Active customers",
      graphiques_a_venir: "Trend charts and detailed tables will be added once the backend is connected.",
    },
  },
  ar: {
    translation: {
      connexion_titre: "تسجيل الدخول",
      connexion_soustitre: "ادخل إلى مساحة العمل الخاصة بك",
      email: "البريد الإلكتروني",
      mot_de_passe: "كلمة المرور",
      se_connecter: "تسجيل الدخول",
      mot_de_passe_oublie: "هل نسيت كلمة المرور؟",
      erreur_identifiants: "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
      marque_titre: "منصة واحدة لكل مؤسستك",
      marque_texte: "المبيعات والمشتريات والمخزون والفواتير في مكان واحد لكل فرق العمل.",
      tableau_de_bord: "لوحة التحكم",
      ventes: "المبيعات",
      achats: "المشتريات",
      stock: "المخزون",
      clients: "العملاء",
      facturation: "الفوترة",
      comptabilite: "المحاسبة",
      parametres: "الإعدادات",
      deconnexion: "تسجيل الخروج",
      rechercher: "بحث...",
      chiffre_affaires: "رقم الأعمال",
      tresorerie: "الخزينة",
      clients_actifs: "العملاء النشطون",
      graphiques_a_venir: "ستتم إضافة الرسوم البيانية والجداول التفصيلية بمجرد ربط الواجهة الخلفية.",
    },
  },
};

i18n.use(initReactI18next).init({
  resources,
  lng: "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false },
});

export default i18n;
