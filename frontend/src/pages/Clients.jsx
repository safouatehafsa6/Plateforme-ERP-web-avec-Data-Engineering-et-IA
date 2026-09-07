import { useTranslation } from "react-i18next";
import PageLayout from "../components/PageLayout";
import TableModule from "../components/TableModule";

const LIGNES = [
  ["STE Sonatrach", "contact@sonatrach.exemple", "+212 6 00 00 00 01", "Actif"],
  ["Enem SPA", "contact@enem.exemple", "+212 6 00 00 00 02", "Actif"],
  ["Sarl Building", "contact@building.exemple", "+212 6 00 00 00 03", "Inactif"],
];

export default function Clients() {
  const { t } = useTranslation();
  return (
    <PageLayout titre={t("clients")}>
      <p className="app-page-note">
        Exemple de données pour valider la structure — sera remplacé par les
        vrais clients une fois le backend connecté.
      </p>
      <TableModule
        colonnes={["Nom", "Email", "Téléphone", "Statut"]}
        lignes={LIGNES}
      />
    </PageLayout>
  );
}
