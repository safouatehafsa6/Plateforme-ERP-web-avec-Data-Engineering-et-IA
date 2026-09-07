import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, ShoppingCart, Truck, Boxes, Users,
  FileText, Wallet, Settings, LogOut,
} from "lucide-react";
import { useTranslation } from "react-i18next";

const ITEMS = [
  { icon: LayoutDashboard, label: "tableau_de_bord", to: "/dashboard" },
  { icon: ShoppingCart, label: "ventes", to: "/ventes" },
  { icon: Truck, label: "achats", to: "/achats" },
  { icon: Boxes, label: "stock", to: "/stock" },
  { icon: Users, label: "clients", to: "/clients" },
  { icon: FileText, label: "facturation", to: "/facturation" },
  { icon: Wallet, label: "comptabilite", to: "/comptabilite" },
];

export default function Sidebar() {
  const { t } = useTranslation();

  return (
    <aside className="app-sidebar">
      <div className="app-sidebar__logo">BENJEDDOU ERP</div>

      <nav className="app-sidebar__nav">
        {ITEMS.map(({ icon: Icon, label, to }) => (
          <NavLink
            key={label}
            to={to}
            className={({ isActive }) =>
              `app-sidebar__item${isActive ? " app-sidebar__item--actif" : ""}`
            }
          >
            <Icon size={18} strokeWidth={1.75} />
            <span>{t(label)}</span>
          </NavLink>
        ))}
      </nav>

      <div className="app-sidebar__bas">
        <NavLink to="/parametres" className="app-sidebar__item">
          <Settings size={18} strokeWidth={1.75} />
          <span>{t("parametres")}</span>
        </NavLink>
        <NavLink to="/" className="app-sidebar__item">
          <LogOut size={18} strokeWidth={1.75} />
          <span>{t("deconnexion")}</span>
        </NavLink>
      </div>
    </aside>
  );
}
