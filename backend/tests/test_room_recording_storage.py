"""Tests du stockage disque des enregistrements Room Live (aucune dépendance externe)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "recording_storage", Path(__file__).resolve().parents[1] / "app" / "services" / "recording_storage.py")
st = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(st)

ROOM = "a" * 12
REC = "b" * 32


class StockageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        st.RECORDINGS_DIR = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chemin_range_par_base_et_salle(self):
        rel = st.relative_path("base_a", ROOM, REC, "video/webm")
        self.assertEqual(rel, f"base_base_a/{ROOM}/{REC}.webm")
        self.assertEqual(st.relative_path(None, ROOM, REC, "audio/webm"), f"central/{ROOM}/{REC}.webm")

    def test_identifiants_invalides_refuses(self):
        for room, rec in (("../etc", REC), (ROOM, "../../passwd"), (ROOM, REC.upper()), ("", REC)):
            with self.assertRaises(st.StorageError):
                st.relative_path("b", room, rec, "video/webm")
        with self.assertRaises(st.StorageError):
            st.relative_path("b/../x", ROOM, REC, "video/webm")
        with self.assertRaises(st.StorageError):
            st.relative_path("b", ROOM, REC, "application/x-sh")

    def test_chemin_hors_racine_refuse(self):
        with self.assertRaises(st.StorageError):
            st.absolute_path("../../etc/passwd")
        with self.assertRaises(st.StorageError):
            st.absolute_path("/etc/passwd")

    def test_ajout_de_fragments_et_taille(self):
        rel = st.relative_path("b", ROOM, REC, "video/webm")
        taille = st.append_chunk(rel, b"abc", 0)
        taille = st.append_chunk(rel, b"de", taille)
        self.assertEqual(taille, 5)
        self.assertEqual(st.absolute_path(rel).read_bytes(), b"abcde")

    def test_limites(self):
        rel = st.relative_path("b", ROOM, REC, "video/webm")
        with self.assertRaises(st.StorageError):
            st.append_chunk(rel, b"", 0)
        with self.assertRaises(st.StorageError):
            st.append_chunk(rel, b"x" * (st.MAX_CHUNK_BYTES + 1), 0)
        with self.assertRaises(st.StorageError):
            st.append_chunk(rel, b"x", st.MAX_RECORDING_BYTES)

    def test_suppression(self):
        rel = st.relative_path("b", ROOM, REC, "video/webm")
        st.append_chunk(rel, b"x", 0)
        self.assertTrue(st.delete_file(rel))
        self.assertFalse(st.absolute_path(rel).exists())
        self.assertFalse(st.delete_file(None))


if __name__ == "__main__":
    unittest.main()
