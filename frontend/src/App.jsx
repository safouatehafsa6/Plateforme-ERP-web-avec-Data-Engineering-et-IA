import { BrowserRouter, Routes, Route } from "react-router-dom";
import { LangueProvider } from "./context/LangueContext";
import Header from "./components/Header";
import Connexion from "./pages/Connexion";
import Inscription from "./pages/Inscription";
import TableauDeBord from "./pages/TableauDeBord";
import Ventes from "./pages/Ventes";
import Achats from "./pages/Achats";
import Stock from "./pages/Stock";
import Clients from "./pages/Clients";
import Facturation from "./pages/Facturation";
import Comptabilite from "./pages/Comptabilite";

// Le Header est rendu une seule fois ici, en dehors des <Routes> :
// il reste donc affiché en continu quelle que soit la page consultée,
// conformément à la demande de l'entreprise (Header fixe global).
export default function App() {
  return (
    <BrowserRouter>
      <LangueProvider>
        <Header />
        <Routes>
          <Route path="/" element={<Connexion />} />
          <Route path="/inscription" element={<Inscription />} />
          <Route path="/dashboard" element={<TableauDeBord />} />
          <Route path="/ventes" element={<Ventes />} />
          <Route path="/achats" element={<Achats />} />
          <Route path="/stock" element={<Stock />} />
          <Route path="/clients" element={<Clients />} />
          <Route path="/facturation" element={<Facturation />} />
          <Route path="/comptabilite" element={<Comptabilite />} />
        </Routes>
      </LangueProvider>
    </BrowserRouter>
  );
}
