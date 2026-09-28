import { useLocation, Link, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, ShoppingCart, Truck, Boxes, Users,
  FileText, Wallet, Settings, LogOut, CreditCard, UserCog, ShieldCheck, Contact,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { lireSession, estAdminEntreprise, estSuperAdmin } from "../api/session";

// `visible` décide si l'entrée apparaît selon le profil connecté.
// Par défaut (pas de `visible`), l'entrée est toujours affichée.
//
// Les pages Collaborateurs et Rôles & Permissions agissent DANS la base
// d'une entreprise : elles ne concernent donc que l'Administrateur Client.
// La page Abonnements est à l'inverse une page de pilotage de la
// plateforme, réservée au Super Administrateur.
const ITEMS = [
  { icon: LayoutDashboard, label: "tableau_de_bord", chemin: "/dashboard" },
  { icon: ShoppingCart, label: "ventes", chemin: "/ventes" },
  { icon: Truck, label: "achats", chemin: "/achats" },
  { icon: Truck, label: "fournisseurs", chemin: "/fournisseurs" },
  { icon: Boxes, label: "stock", chemin: "/stock" },
  { icon: Users, label: "clients", chemin: "/clients" },
  { icon: FileText, label: "facturation", chemin: "/facturation" },
  { icon: Wallet, label: "comptabilite", chemin: "/comptabilite" },
  { icon: UserCog, label: "collaborateurs_titre", chemin: "/collaborateurs", visible: estAdminEntreprise },
  { icon: ShieldCheck, label: "roles_permissions_titre", chemin: "/roles-permissions", visible: estAdminEntreprise },
  { icon: Contact, label: "utilisateurs_externes_titre", chemin: "/utilisateurs-externes", visible: estAdminEntreprise },
  { icon: CreditCard, label: "admin_abonnements_titre", chemin: "/admin/abonnements", visible: estSuperAdmin },
];

export default function Sidebar() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const session = lireSession();

  let featureState = {};
  try { featureState = JSON.parse(localStorage.getItem("erp_features") || "{}"); } catch {}
  const items = ITEMS.filter(({ visible, label }) => {
    if (visible && !visible(session)) return false;
    return featureState[label] !== false;
  });

  function deconnexion(e) {
    e.preventDefault();
    localStorage.removeItem("token");
    navigate("/");
  }

  return (
    <aside className="app-sidebar">
      <div className="app-sidebar__logo">BENJEDDOU ERP</div>

      <nav className="app-sidebar__nav">
        {items.map(({ icon: Icon, label, chemin }) => (
          <Link
            key={label}
            to={chemin}
            className={`app-sidebar__item${location.pathname === chemin ? " app-sidebar__item--actif" : ""}`}
          >
            <Icon size={18} strokeWidth={1.75} />
            <span>{t(label)}</span>
          </Link>
        ))}
      </nav>

      <div className="app-sidebar__bas">
        <Link
          to="/parametres"
          className={`app-sidebar__item${location.pathname === "/parametres" ? " app-sidebar__item--actif" : ""}`}
        >
          <Settings size={18} strokeWidth={1.75} />
          <span>{t("parametres")}</span>
        </Link>
        <a href="#" className="app-sidebar__item" onClick={deconnexion}>
          <LogOut size={18} strokeWidth={1.75} />
          <span>{t("deconnexion")}</span>
        </a>
      </div>
    </aside>
  );
}
