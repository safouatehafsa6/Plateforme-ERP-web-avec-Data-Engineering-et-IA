import { BrowserRouter, Routes, Route } from "react-router-dom";
import { LangueProvider } from "./context/LangueContext";
import { ThemeProvider } from "./context/ThemeContext";
import Header from "./components/Header";
import Connexion from "./pages/Connexion";
import Inscription from "./pages/Inscription";
import MotDePasseOublie from "./pages/MotDePasseOublie";
import TableauDeBord from "./pages/TableauDeBord";
import AdminAbonnements from "./pages/AdminAbonnements";
import Collaborateurs from "./pages/Collaborateurs";
import RolesPermissions from "./pages/RolesPermissions";
import UtilisateursExternes from "./pages/UtilisateursExternes";
import PortailAccueil from "./pages/PortailAccueil";

// Le Header est rendu une seule fois ici, en dehors des <Routes> :
// il reste donc affiché en continu quelle que soit la page consultée,
// conformément à la demande de l'entreprise (Header fixe global).
export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <LangueProvider>
          <Header />
          <Routes>
            <Route path="/" element={<Connexion />} />
            <Route path="/inscription" element={<Inscription />} />
            <Route path="/mot-de-passe-oublie" element={<MotDePasseOublie />} />
            <Route path="/dashboard" element={<TableauDeBord />} />
            <Route path="/admin/abonnements" element={<AdminAbonnements />} />
            <Route path="/collaborateurs" element={<Collaborateurs />} />
            <Route path="/roles-permissions" element={<RolesPermissions />} />
            <Route path="/utilisateurs-externes" element={<UtilisateursExternes />} />
            <Route path="/portail" element={<PortailAccueil />} />
          </Routes>
        </LangueProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
