"""IDP -> Achats : rapprochement, choix obligatoires, transaction unique, une seule intégration par document.

Les fonctions pures sont testées directement ; `integrer` est testé avec un faux curseur SQL qui
rejoue les requêtes dans une mini base en mémoire (aucun PostgreSQL nécessaire)."""
import sys
import types
import unittest
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from unittest import mock

# Aucun faux module n'est installé dans sys.modules au chargement : un faux « minio » masquerait le vrai
# pour les autres tests (import de app.main). idp_stockage n'importe MinIO qu'à l'usage.
from app.services import idp_integration as it

PRODUITS = [
    {"id": 1, "reference": "STY-01", "nom": "Stylo bleu"},
    {"id": 2, "reference": "CAH-A4", "nom": "Cahier A4 96 pages"},
]
FOURNISSEURS = [{"id": 10, "nom": "Papeterie Atlas SARL"}, {"id": 11, "nom": "Bureau Plus"}]


def doc(**kw):
    base = {"type_document": "facture", "numero": "F-42", "date": "2026-11-09", "devise": "MAD",
            "fournisseur": {"nom": "Papeterie ATLAS"},
            "lignes": [{"designation": "Stylo bleu", "quantite": "10", "prix_unitaire": "2,50", "taux_tva": "20"},
                       {"designation": "Ramette papier 500 feuilles", "quantite": 5, "prix_unitaire": 40}]}
    base.update(kw)
    return base


class FonctionsPuresTests(unittest.TestCase):
    def test_types_integrables(self):
        self.assertEqual(it.type_integrable({"type_document": "facture"})[0], "facture")
        self.assertEqual(it.type_integrable({"type_document": "Bon de commande"})[0], "bon_commande")
        self.assertEqual(it.type_integrable({"type_document": "devis"})[0], "devis")
        self.assertEqual(it.type_integrable({"type_document": "فاتورة"})[0], "facture")
        for refus in ({"type_document": "avoir"}, {"type_document": "rapport de stage"}, {}):
            self.assertIsNone(it.type_integrable(refus)[0])
            self.assertTrue(it.type_integrable(refus)[1])

    def test_statut_cible(self):
        self.assertEqual(it.STATUT_ACHAT, {"facture": "facture", "bon_commande": "commande", "devis": "en_cours"})

    def test_fournisseur_trouve_suggere_ou_a_creer(self):
        self.assertEqual(it.rapprocher_fournisseur("PAPETERIE ATLAS", FOURNISSEURS)["statut"], "trouve")  # forme juridique ignorée
        self.assertEqual(it.rapprocher_fournisseur("Papeterie Atlass", FOURNISSEURS)["statut"], "suggere")
        self.assertEqual(it.rapprocher_fournisseur("Totalement Autre", FOURNISSEURS)["statut"], "a_creer")
        self.assertEqual(it.rapprocher_fournisseur(None, FOURNISSEURS)["statut"], "a_creer")

    def test_produit_par_nom_reference_ou_similarite(self):
        self.assertEqual(it.rapprocher_produit("stylo  BLEU", PRODUITS)["id"], 1)
        self.assertEqual(it.rapprocher_produit("Lot de cahier CAH-A4 pour bureau", PRODUITS)["id"], 2)
        self.assertEqual(it.rapprocher_produit("Stylo bleu.", PRODUITS)["statut"], "trouve")
        self.assertEqual(it.rapprocher_produit("Cahier A4 96 page", PRODUITS)["statut"], "suggere")
        self.assertEqual(it.rapprocher_produit("Ramette papier", PRODUITS)["statut"], "a_creer")

    def test_preparer_lignes(self):
        lignes = it.preparer_lignes(doc(), PRODUITS)
        self.assertEqual(lignes[0]["quantite"], 10)
        self.assertEqual(lignes[0]["prix_unitaire"], "2.50")
        self.assertEqual(lignes[0]["produit"]["id"], 1)
        self.assertEqual(lignes[1]["produit"]["statut"], "a_creer")
        self.assertEqual(lignes[0]["problemes"], [])

    def test_lignes_problematiques_signalees(self):
        mauvaises = doc(lignes=[{"designation": "A", "quantite": "2,5", "prix_unitaire": 3},
                                {"designation": "", "quantite": 1, "prix_unitaire": 3},
                                {"designation": "B", "quantite": 0, "prix_unitaire": 3},
                                {"designation": "C", "quantite": 1}])
        for ligne in it.preparer_lignes(mauvaises, PRODUITS):
            self.assertTrue(ligne["problemes"], ligne)

    def test_prix_deduit_du_total_si_absent(self):
        ligne = it.preparer_lignes(doc(lignes=[{"designation": "A", "quantite": 4, "total_ht": "100"}]), PRODUITS)[0]
        self.assertEqual(ligne["prix_unitaire"], "25.00")

    def test_choix_obligatoires_pour_chaque_ligne(self):
        lignes = it.preparer_lignes(doc(), PRODUITS)
        with self.assertRaises(it.IntegrationErreur):                               # ligne 2 sans décision
            it.valider_choix(lignes, {"lignes": [{"index": 0, "produit_id": 1}]}, {1, 2})
        with self.assertRaises(it.IntegrationErreur):                               # produit inexistant
            it.valider_choix(lignes, {"lignes": [{"index": 0, "produit_id": 99}, {"index": 1, "creer": True}]}, {1, 2})
        ok = it.valider_choix(lignes, {"lignes": [{"index": 0, "produit_id": 1}, {"index": 1, "creer": True}]}, {1, 2})
        self.assertEqual([l["creer"] for l in ok], [False, True])


class FauxCurseur:
    """Mini base en mémoire qui reconnaît les requêtes d'`integrer` (par sous-chaîne)."""

    def __init__(self, base):
        self.b, self.res, self.description = base, [], None

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).lower()
        b = self.b
        self.res, self.description = [], None
        if s.startswith("create table"):
            return
        if "from idp_documents" in s and "for update" in s:
            self.res = [tuple(b["document"][c] for c in b["colonnes"])] if b.get("document") else []
        elif "from idp_integrations" in s:
            self.res = [(b["integration"],)] if b.get("integration") else []
        elif s.startswith("select id, reference, nom from produit"):
            self.res = [(p["id"], p["reference"], p["nom"]) for p in b["produits"]]
            self.description = [("id",), ("reference",), ("nom",)]
        elif s.startswith("select id from fournisseur"):
            self.res = [(params[0],)] if any(f["id"] == params[0] for f in b["fournisseurs"]) else []
        elif s.startswith("insert into fournisseur"):
            b["fournisseurs"].append({"id": 100 + len(b["fournisseurs"]), "nom": params[0]})
            self.res = [(b["fournisseurs"][-1]["id"],)]
        elif s.startswith("select 1 from produit where reference"):
            self.res = [(1,)] if any(p["reference"] == params[0] for p in b["produits"]) else []
        elif s.startswith("insert into produit"):
            b["produits"].append({"id": 200 + len(b["produits"]), "reference": params[0], "nom": params[1]})
            b["crees"].append(params)
            self.res = [(b["produits"][-1]["id"],)]
        elif "nextval('seq_achat_numero')" in s:
            self.res = [(7,)]
        elif s.startswith("insert into achat"):
            b["achat"] = params
            self.res = [(55,)]
        elif s.startswith("insert into ligne_achat"):
            b["lignes_achat"] = params
        elif "from ligne_achat la join produit" in s:
            self.res = [(1, "x", 10, Decimal("2.50"), Decimal("0"), None)]
            self.description = [("produit_id",), ("designation",), ("quantite",), ("prix_unitaire",), ("remise_pct",), ("taux_tva",)]
        elif s.startswith("update achat"):
            b["achat_maj"] = params
        elif s.startswith("insert into idp_integrations"):
            b["integration_creee"] = params
        elif s.startswith("insert into idp_evenements"):
            b["evenements"].append(params[1])
        else:
            raise AssertionError("requête inattendue : " + s[:80])

    def executemany(self, sql, seq):
        self.execute(sql, list(seq))

    def fetchone(self):
        return self.res[0] if self.res else None

    def fetchall(self):
        return list(self.res)


def base_en_memoire(document):
    colonnes = ("id", "empreinte_fichier", "empreinte_metier", "nom_fichier", "format", "taille_octets", "cle_stockage",
                "statut", "donnees", "anomalies", "avertissements", "modele", "ocr_utilise", "depose_par", "depose_le",
                "traite_par", "traite_le", "motif_rejet")
    brut = {c: None for c in colonnes}
    brut.update(id=5, nom_fichier="facture.pdf", statut="valide", donnees=document, anomalies=[], avertissements=[],
                depose_le=datetime(2026, 11, 9))
    return {"colonnes": colonnes, "document": brut, "produits": [dict(p) for p in PRODUITS],
            "fournisseurs": [dict(f) for f in FOURNISSEURS], "crees": [], "evenements": []}


class IntegrerTests(unittest.TestCase):
    def lancer(self, base, choix, statut="valide"):
        if base["document"]:
            base["document"]["statut"] = statut
        curseur = FauxCurseur(base)

        @contextmanager
        def transaction(pool):
            yield curseur

        calcul = mock.Mock(return_value={"montant_ht": Decimal("25.00"), "montant_tva": Decimal("5.00"),
                                         "montant_ttc": Decimal("30.00")})
        faux_moteur = types.SimpleNamespace(assurer_schema=lambda *a, **k: None, calculer_document=calcul)
        with mock.patch.object(it.idp_stockage, "_transaction", transaction), \
                mock.patch.object(it.idp_stockage, "initialiser_schema", lambda pool: None), \
                mock.patch.dict(sys.modules, {"app.services.moteur_regles_metier": faux_moteur}):
            return it.integrer("POOL", "base_x", 5, choix, "3"), calcul

    CHOIX = {"fournisseur_id": 10, "lignes": [{"index": 0, "produit_id": 1}, {"index": 1, "creer": True}]}

    def test_integration_complete(self):
        base = base_en_memoire(doc())
        resultat, calcul = self.lancer(base, self.CHOIX)
        self.assertEqual(resultat["numero"].split("-")[0], "ACH")
        self.assertEqual(resultat["statut"], "facture")
        self.assertEqual(resultat["produits_crees"], 1)
        self.assertFalse(resultat["fournisseur_cree"])
        self.assertEqual(resultat["montant_ttc"], "30.00")
        self.assertEqual(len(base["lignes_achat"]), 2)                    # 2 lignes insérées
        self.assertIn("document IDP n°5", base["achat"][3])                # traçabilité dans les notes
        self.assertEqual(base["integration_creee"][1], "achats")           # lien document <-> achat
        self.assertEqual(base["evenements"], ["integration_achats"])
        calcul.assert_called_once()
        self.assertTrue(base["crees"][0][0].startswith("IDP-5-2"))         # référence du produit créé

    def test_creation_du_fournisseur_apres_confirmation(self):
        base = base_en_memoire(doc(fournisseur={"nom": "Nouveau Fournisseur"}))
        resultat, _ = self.lancer(base, {"creer_fournisseur": True, "lignes": self.CHOIX["lignes"]})
        self.assertTrue(resultat["fournisseur_cree"])
        self.assertEqual(base["fournisseurs"][-1]["nom"], "Nouveau Fournisseur")

    def test_sans_choix_de_fournisseur_rien_n_est_cree(self):
        base = base_en_memoire(doc())
        with self.assertRaises(it.IntegrationErreur) as ctx:
            self.lancer(base, {"lignes": self.CHOIX["lignes"]})
        self.assertEqual(ctx.exception.statut, 400)
        self.assertNotIn("achat", base)

    def test_document_non_valide_refuse(self):
        base = base_en_memoire(doc())
        with self.assertRaises(it.IntegrationErreur) as ctx:
            self.lancer(base, self.CHOIX, statut="brouillon")
        self.assertEqual(ctx.exception.statut, 409)
        self.assertNotIn("achat", base)

    def test_deuxieme_integration_refusee(self):
        base = base_en_memoire(doc())
        base["integration"] = "ACH-2026-000003"
        with self.assertRaises(it.IntegrationErreur) as ctx:
            self.lancer(base, self.CHOIX)
        self.assertEqual(ctx.exception.statut, 409)
        self.assertIn("ACH-2026-000003", ctx.exception.detail)

    def test_type_non_integrable_refuse(self):
        base = base_en_memoire(doc(type_document="rapport de stage"))
        with self.assertRaises(it.IntegrationErreur):
            self.lancer(base, self.CHOIX)

    def test_document_introuvable(self):
        base = base_en_memoire(doc())
        base["document"] = None
        with self.assertRaises(it.IntegrationErreur) as ctx:
            self.lancer(base, self.CHOIX)
        self.assertEqual(ctx.exception.statut, 404)


if __name__ == "__main__":
    unittest.main()
