import { useTranslation } from "react-i18next";
import { Search, Bell } from "lucide-react";
import Sidebar from "./Sidebar";

export default function PageLayout({ titre, children }) {
  const { t } = useTranslation();

  return (
    <div className="app-layout">
      <Sidebar />

      <div className="app-contenu">
        <header className="app-topbar">
          <div className="app-topbar__recherche">
            <Search size={16} strokeWidth={1.75} />
            <input type="text" placeholder={t("rechercher")} />
          </div>
          <div className="app-topbar__droite">
            <Bell size={18} strokeWidth={1.75} />
            <div className="app-topbar__avatar">A</div>
          </div>
        </header>

        <main className="app-main">
          <h1 className="app-main__titre">{titre}</h1>
          {children}
        </main>
      </div>
    </div>
  );
}
