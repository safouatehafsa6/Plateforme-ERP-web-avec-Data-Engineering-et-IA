import {
  LayoutDashboard, ShoppingCart, Truck, Boxes, Users,
  FileText, Wallet, Settings, LogOut,
} from "lucide-react";
import { useTranslation } from "react-i18next";

const ITEMS = [
  { icon: LayoutDashboard, label: "tableau_de_bord", actif: true },
  { icon: ShoppingCart, label: "ventes" },
  { icon: Truck, label: "achats" },
  { icon: Boxes, label: "stock" },
  { icon: Users, label: "clients" },
  { icon: FileText, label: "facturation" },
  { icon: Wallet, label: "comptabilite" },
];

export default function Sidebar() {
  const { t } = useTranslation();

  return (
    <aside className="app-sidebar">
      <div className="app-sidebar__logo">BENJEDDOU ERP</div>

      <nav className="app-sidebar__nav">
        {ITEMS.map(({ icon: Icon, label, actif }) => (
          <a key={label} href="#" className={`app-sidebar__item${actif ? " app-sidebar__item--actif" : ""}`}>
            <Icon size={18} strokeWidth={1.75} />
            <span>{t(label)}</span>
          </a>
        ))}
      </nav>

      <div className="app-sidebar__bas">
        <a href="#" className="app-sidebar__item">
          <Settings size={18} strokeWidth={1.75} />
          <span>{t("parametres")}</span>
        </a>
        <a href="#" className="app-sidebar__item">
          <LogOut size={18} strokeWidth={1.75} />
          <span>{t("deconnexion")}</span>
        </a>
      </div>
    </aside>
  );
}
