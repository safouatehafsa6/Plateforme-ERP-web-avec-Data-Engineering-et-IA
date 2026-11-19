
import base64
import secrets
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.security import crypto
from app.services import sauvegardes


@pytest.fixture
def environnement_sauvegarde(monkeypatch, tmp_path):
    monkeypatch.setenv("ERP_BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv(
        "ERP_HMAC_KEY",
        base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    )
    return tmp_path


def creer_fichier_sauvegarde(repertoire, db_name, contenu, contexte):
    filename = (
        f"{db_name}_20261119_120000_a1b2c3d4.bak.enc"
    )
    path = repertoire / filename
    path.write_bytes(contenu)

    signature = crypto.signer(contenu, context=contexte)
    path.with_suffix(path.suffix + ".hmac").write_text(
        signature, encoding="ascii"
    )
    return filename


def test_signature_hmac_isole_les_entreprises(
    environnement_sauvegarde
):
    contenu = b"sauvegarde de test"
    signature = crypto.signer(contenu, context="entreprise_a")

    assert crypto.verifier_signature(
        contenu, signature, context="entreprise_a"
    )
    assert not crypto.verifier_signature(
        contenu, signature, context="entreprise_b"
    )


def test_obtenir_chemins_refuse_une_autre_entreprise(
    environnement_sauvegarde
):
    filename = (
        "entreprise_b_20261119_120000_a1b2c3d4.bak.enc"
    )

    with pytest.raises(ValueError):
        sauvegardes._obtenir_chemins(
            filename, "entreprise_a"
        )


def test_obtenir_chemins_refuse_un_fichier_absent(
    environnement_sauvegarde
):
    filename = (
        "entreprise_a_20261119_120000_a1b2c3d4.bak.enc"
    )

    with pytest.raises(FileNotFoundError):
        sauvegardes._obtenir_chemins(
            filename, "entreprise_a"
        )


def test_verifier_sauvegarde_refuse_hmac_d_un_autre_tenant(
    environnement_sauvegarde, monkeypatch
):
    filename = creer_fichier_sauvegarde(
        environnement_sauvegarde,
        "entreprise_b",
        b"contenu chiffre simule",
        "entreprise_a"
    )

    def dechiffrement_interdit(blob):
        pytest.fail("Le déchiffrement ne doit pas être exécuté.")

    monkeypatch.setattr(
        sauvegardes, "dechiffrer", dechiffrement_interdit
    )

    with pytest.raises(ValueError, match="HMAC"):
        sauvegardes.verifier_sauvegarde(
            filename, "entreprise_b"
        )


def test_creer_sauvegarde_chiffre_et_signe(
    environnement_sauvegarde, monkeypatch
):
    def faux_pg_dump(cmd, **kwargs):
        chemin_dump = Path(cmd[cmd.index("--file") + 1])
        chemin_dump.write_bytes(b"dump PostgreSQL simule")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(
        sauvegardes.subprocess, "run", faux_pg_dump
    )
    monkeypatch.setattr(
        sauvegardes, "chiffrer",
        lambda contenu: b"contenu chiffre simule"
    )

    resultat = sauvegardes.creer_sauvegarde("entreprise_a")

    assert resultat["base"] == "entreprise_a"
    assert resultat["chiffre"] is True

    path = environnement_sauvegarde / resultat["fichier"]
    signature_path = path.with_suffix(path.suffix + ".hmac")

    assert path.is_file()
    assert signature_path.is_file()

    signature = signature_path.read_text(encoding="ascii")
    assert crypto.verifier_signature(
        path.read_bytes(),
        signature,
        context="entreprise_a"
    )


def test_restaurer_refuse_une_confirmation_incorrecte(
    monkeypatch
):
    def operation_interdite(*args, **kwargs):
        pytest.fail("Aucune sauvegarde ne doit être créée.")

    monkeypatch.setattr(
        sauvegardes, "verifier_sauvegarde", operation_interdite
    )
    monkeypatch.setattr(
        sauvegardes, "creer_sauvegarde", operation_interdite
    )

    with pytest.raises(ValueError, match="Confirmation"):
        sauvegardes.restaurer_sauvegarde(
            "entreprise_a_20261119_120000_a1b2c3d4.bak.enc",
            "entreprise_a",
            "CONFIRMATION INCORRECTE"
        )
