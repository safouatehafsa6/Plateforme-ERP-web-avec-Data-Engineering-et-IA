import { BrowserRouter, Routes, Route } from "react-router-dom";
import Connexion from "./pages/Connexion";
import TableauDeBord from "./pages/TableauDeBord";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Connexion />} />
        <Route path="/dashboard" element={<TableauDeBord />} />
      </Routes>
    </BrowserRouter>
  );
}
