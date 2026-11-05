import unittest

from app.routers.assistant import _fallback_understanding, _intent


class AssistantIntentTests(unittest.TestCase):
    def test_order_creation_paraphrases_map_to_same_intent(self):
        messages = (
            "Je veux créer une commande",
            "Je veux faire une commande",
            "Je voudrais passer une nouvelle commande",
            "Je souhaite préparer une commande",
            "Please make an order",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(_fallback_understanding(message)["intent"], "create_commande")

    def test_client_and_supplier_intents(self):
        self.assertEqual(_intent("Je veux créer un client"), "create_client")
        self.assertEqual(_intent("Ajouter un fournisseur"), "create_fournisseur")
        self.assertEqual(_intent("Rechercher un client"), "search_client")
        self.assertEqual(_intent("Modifier un fournisseur"), "edit_fournisseur")

    def test_extracts_order_entities(self):
        result = _fallback_understanding("Je veux faire une commande pour le client Atlas")
        self.assertEqual(result["intent"], "create_commande")
        self.assertEqual(result["entities"].get("client_name"), "Atlas")

    def test_unrelated_message_does_not_start_workflow(self):
        self.assertIsNone(_intent("Bonjour, comment ça va ?"))


if __name__ == "__main__":
    unittest.main()
