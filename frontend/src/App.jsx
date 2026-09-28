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
import VerificationDocument from "./pages/VerificationDocument";
import Ventes from "./pages/Ventes";
import Achats from "./pages/Achats";
import Fournisseurs from "./pages/Fournisseurs";
import Clients from "./pages/Clients";
import Stock from "./pages/Stock";
import Parametres from "./pages/Parametres";
import Facturation from "./pages/Facturation";
import Comptabilite from "./pages/Comptabilite";

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
            <Route path="/ventes" element={<Ventes />} />
            <Route path="/achats" element={<Achats />} />
            <Route path="/fournisseurs" element={<Fournisseurs />} />
            <Route path="/clients" element={<Clients />} />
            <Route path="/stock" element={<Stock />} />
            <Route path="/parametres" element={<Parametres />} />
            <Route path="/facturation" element={<Facturation />} />
            <Route path="/comptabilite" element={<Comptabilite />} />
            <Route path="/admin/abonnements" element={<AdminAbonnements />} />
            <Route path="/collaborateurs" element={<Collaborateurs />} />
            <Route path="/roles-permissions" element={<RolesPermissions />} />
            <Route path="/utilisateurs-externes" element={<UtilisateursExternes />} />
            <Route path="/portail" element={<PortailAccueil />} />
            <Route path="/verifier/:nomBase/:code" element={<VerificationDocument />} />
          </Routes>
        </LangueProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
