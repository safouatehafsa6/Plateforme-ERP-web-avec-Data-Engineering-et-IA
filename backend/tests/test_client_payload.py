import unittest

from pydantic import ValidationError

from app.schemas.clients import ClientPayload


class ClientPayloadTests(unittest.TestCase):
    def test_strips_name_and_converts_empty_optional_fields_to_none(self):
        client = ClientPayload(nom="  Client Atlas  ", email="  ", telephone="", adresse=" ")
        self.assertEqual(client.nom, "Client Atlas")
        self.assertIsNone(client.email)
        self.assertIsNone(client.telephone)
        self.assertIsNone(client.adresse)

    def test_rejects_blank_name(self):
        with self.assertRaises(ValidationError):
            ClientPayload(nom="   ")

    def test_rejects_invalid_email(self):
        with self.assertRaises(ValidationError):
            ClientPayload(nom="Atlas", email="not-an-email")

    def test_accepts_valid_email(self):
        client = ClientPayload(nom="Atlas", email="contact@atlas.example")
        self.assertEqual(client.email, "contact@atlas.example")

    def test_accepts_international_phone(self):
        client = ClientPayload(nom="Atlas", telephone="+212 6 12 34 56 78")
        self.assertEqual(client.telephone, "+212 6 12 34 56 78")

    def test_rejects_phone_with_letters_and_too_few_digits(self):
        for phone in ("06ABC123", "12345"):
            with self.subTest(phone=phone):
                with self.assertRaises(ValidationError):
                    ClientPayload(nom="Atlas", telephone=phone)

    def test_limits_address_length(self):
        with self.assertRaises(ValidationError):
            ClientPayload(nom="Atlas", adresse="A" * 1001)


if __name__ == "__main__":
    unittest.main()
