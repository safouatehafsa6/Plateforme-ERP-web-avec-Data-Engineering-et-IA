import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.schemas.boutons_flottants import BoutonPayload, ConfigPayload, OrdrePayload
from app.services import boutons_flottants as r


def payload(**extra):
    base = dict(titres={"fr": "Promo"}, icone="gift", action="route", cible="/clients")
    base.update(extra)
    return BoutonPayload(**base)


class CibleTests(unittest.TestCase):
    def test_actions_integrees_sans_cible(self):
        for action in r.ACTIONS_INTEGREES:
            self.assertIsNone(r.verifier_cible(action, None))
            self.assertIsNotNone(r.verifier_cible(action, "/x"))

    def test_route_interne(self):
        for ok in ("/", "/clients", "/admin/abonnements", "/calculs?type=taux", "/room-live#salle"):
            self.assertIsNone(r.verifier_cible("route", ok), ok)
        for ko in (None, "", "clients", "//evil.com", "/../etc/passwd", "javascript:alert(1)", "/a b", "https://x.tn", "/" + "a" * 250):
            self.assertIsNotNone(r.verifier_cible("route", ko), ko)

    def test_lien_externe_n_accepte_que_https_mailto_tel(self):
        for ok in ("https://exemple.tn/offre", "mailto:contact@exemple.tn", "tel:+21612345678"):
            self.assertIsNone(r.verifier_cible("url", ok), ok)
        for ko in ("http://exemple.tn", "javascript:alert(1)", "data:text/html,x", "ftp://x.tn", "https://", "//x.tn", "https:// x", None):
            self.assertIsNotNone(r.verifier_cible("url", ko), ko)

    def test_whatsapp(self):
        self.assertIsNone(r.verifier_cible("whatsapp", None))           # numéro de la plateforme
        self.assertIsNone(r.verifier_cible("whatsapp", "+216 12 345 678"))
        self.assertIsNotNone(r.verifier_cible("whatsapp", "12ab"))
        self.assertEqual(r.normaliser_cible("whatsapp", "+216 12 345 678"), "21612345678")

    def test_nouvel_onglet_reserve_aux_liens_externes(self):
        self.assertIsNotNone(r.verifier_cible("route", "/clients", nouvel_onglet=True))
        self.assertIsNone(r.verifier_cible("url", "https://exemple.tn", nouvel_onglet=True))

    def test_cle_et_couleur(self):
        self.assertEqual(r.generer_cle("Promo Été ! 2026"), "promo-ete-2026")
        self.assertEqual(r.generer_cle("!!"), "bouton")
        self.assertTrue(r.couleur_valide("#A1b2C3") and r.couleur_valide(None))
        self.assertFalse(r.couleur_valide("red") or r.couleur_valide("#12345") or r.couleur_valide("#12345g"))


class PayloadTests(unittest.TestCase):
    def test_valide_et_normalise(self):
        p = payload(couleur="#AABBCC", titres={"fr": " Promo ", "en": "", "ar": "عرض"})
        self.assertEqual(p.titres, {"fr": "Promo", "ar": "عرض"})
        self.assertEqual(p.couleur, "#aabbcc")
        self.assertEqual((p.placement, p.position, p.audience, p.profils), ("menu", None, "tous", []))

    def test_titre_francais_obligatoire_et_borne(self):
        for titres in ({}, {"en": "Promo"}, {"fr": "  "}, {"fr": "x" * 41}, {"fr": "ok", "de": "nein"}):
            with self.assertRaises(ValidationError, msg=str(titres)):
                payload(titres=titres)

    def test_listes_blanches(self):
        for champ, valeur in (("icone", "skull"), ("taille", "geant"), ("action", "eval"), ("audience", "vip"),
                              ("appareils", "tv"), ("couleur", "red"), ("ordre", -1), ("ordre", 10000)):
            with self.assertRaises(ValidationError, msg=f"{champ}={valeur}"):
                payload(**{champ: valeur})

    def test_cible_incoherente_avec_l_action(self):
        with self.assertRaises(ValidationError):
            payload(action="url", cible="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            payload(action="support", cible="/clients")
        with self.assertRaises(ValidationError):
            payload(action="route", cible="//evil.tn")

    def test_bouton_libre_exige_une_position(self):
        with self.assertRaises(ValidationError):
            payload(placement="libre")
        self.assertEqual(payload(placement="libre", position="haut-gauche").position, "haut-gauche")
        self.assertIsNone(payload(placement="menu", position="haut-gauche").position)   # ignorée dans le menu

    def test_audience_et_profils(self):
        with self.assertRaises(ValidationError):
            payload(audience="public", profils=["interne"])
        with self.assertRaises(ValidationError):
            payload(action="notifications", cible=None, audience="public")
        with self.assertRaises(ValidationError):
            payload(profils=["pirate"])
        self.assertEqual(payload(profils=["interne", "interne", "externe"]).profils, ["interne", "externe"])

    def test_pages_et_dates(self):
        self.assertEqual(payload(routes_incluses=["/clients", " /ventes ", "/clients"]).routes_incluses, ["/clients", "/ventes"])
        for ko in (["clients"], ["/a/../b"], ["/x y"], ["/" + "a" * 120], [f"/p{i}" for i in range(21)]):
            with self.assertRaises(ValidationError, msg=str(ko)):
                payload(routes_exclues=ko)
        d1, d2 = datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc)
        self.assertIsNotNone(payload(affiche_du=d1, affiche_jusqu_au=d2))
        with self.assertRaises(ValidationError):
            payload(affiche_du=d2, affiche_jusqu_au=d1)

    def test_config_et_ordre(self):
        self.assertEqual(ConfigPayload().position, "auto")
        with self.assertRaises(ValidationError):
            ConfigPayload(position="plafond")
        with self.assertRaises(ValidationError):
            ConfigPayload(couleur="bleu")
        with self.assertRaises(ValidationError):
            OrdrePayload(ids=[1, 1])
        with self.assertRaises(ValidationError):
            OrdrePayload(ids=[])

    def test_defauts_systeme_valides(self):
        cles = set()
        for b in r.DEFAUTS_SYSTEME:
            p = BoutonPayload(**{k: v for k, v in b.items() if k != "cle"})
            self.assertEqual(p.titres["fr"], b["titres"]["fr"])
            self.assertEqual(set(b["titres"]), set(r.LANGUES))
            cles.add(b["cle"])
        self.assertEqual(len(cles), len(r.DEFAUTS_SYSTEME))


if __name__ == "__main__":
    unittest.main()
