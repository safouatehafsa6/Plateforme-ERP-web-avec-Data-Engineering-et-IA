
"""Sauvegardes PostgreSQL chiffrées et vérifiables via pg_dump/pg_restore."""
import os
import pathlib
import re
import subprocess
import tempfile
import time
import uuid

from app.security.crypto import chiffrer, dechiffrer, signer, verifier_signature


def _valider_nom_base(db_name: str) -> None:
    if not isinstance(db_name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", db_name):
        raise ValueError("Nom de base invalide.")


def _dir():
    p = pathlib.Path(os.getenv("ERP_BACKUP_DIR", "/app/backups"))
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return p


def _obtenir_chemins(filename: str, db_name: str):
    """Vérifie le format et l'appartenance de la sauvegarde au tenant."""
    _valider_nom_base(db_name)

    if not isinstance(filename, str):
        raise ValueError("Nom de sauvegarde invalide.")

    motif = (
        re.escape(db_name)
        + r"_\d{8}_\d{6}_[0-9a-f]{8}\.bak\.enc"
    )

    if not re.fullmatch(motif, filename):
        raise ValueError("Cette sauvegarde n'appartient pas à cette entreprise.")

    repertoire = _dir()
    path = repertoire / filename
    sigpath = path.with_suffix(path.suffix + ".hmac")

    if not path.is_file() or not sigpath.is_file():
        raise FileNotFoundError("Sauvegarde ou signature absente.")

    return path, sigpath


def obtenir_fichiers_sauvegarde(filename: str, db_name: str):
    """Accès aux fichiers uniquement après vérification du tenant."""
    return _obtenir_chemins(filename, db_name)


def creer_sauvegarde(db_name: str) -> dict:
    _valider_nom_base(db_name)

    with tempfile.TemporaryDirectory() as tmp:
        raw = pathlib.Path(tmp) / "db.dump"
        env = os.environ.copy()

        cmd = [
            "pg_dump", "--format=custom", "--no-owner", "--no-acl",
            "--file", str(raw),
            "-h", env.get("DB_HOST", "postgres-erp"),
            "-p", env.get("DB_PORT", "5432"),
            "-U", env.get("DB_USER", "erp_user"),
            db_name,
        ]

        env["PGPASSWORD"] = env.get("DB_PASSWORD", "")
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=900
        )

        if result.returncode:
            raise RuntimeError("Échec de la création de la sauvegarde PostgreSQL.")

        plain = raw.read_bytes()

    encrypted = chiffrer(plain)
    name = (
        f"{db_name}_{time.strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}.bak.enc"
    )

    target = _dir() / name
    target.write_bytes(encrypted)
    os.chmod(target, 0o600)

    signature = signer(encrypted, context=db_name)
    sigpath = target.with_suffix(target.suffix + ".hmac")
    sigpath.write_text(signature, encoding="ascii")
    os.chmod(sigpath, 0o600)

    return {
        "fichier": name,
        "base": db_name,
        "taille": len(encrypted),
        "hmac_sha256": signature,
        "chiffre": True,
    }


def verifier_sauvegarde(filename: str, db_name: str) -> dict:
    path, sigpath = _obtenir_chemins(filename, db_name)

    blob = path.read_bytes()
    signature = sigpath.read_text(encoding="ascii").strip()

    if not verifier_signature(blob, signature, context=db_name):
        raise ValueError("Échec HMAC : fichier modifié ou clé incorrecte.")

    plain = dechiffrer(blob)

    with tempfile.NamedTemporaryFile(suffix=".dump") as f:
        f.write(plain)
        f.flush()

        env = os.environ.copy()
        env["PGPASSWORD"] = env.get("DB_PASSWORD", "")

        result = subprocess.run(
            ["pg_restore", "--list", f.name],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode:
            raise ValueError(
                "Le contenu PostgreSQL n'est pas un dump restaurable."
            )

    return {
        "fichier": filename,
        "integrite": "valide",
        "dechiffrement": "valide",
        "format": "PostgreSQL custom",
    }


def restaurer_sauvegarde(
    filename: str, db_name: str, confirmation: str
) -> dict:
    _valider_nom_base(db_name)

    if confirmation != f"RESTAURER {db_name}":
        raise ValueError("Confirmation textuelle incorrecte.")

    verifier_sauvegarde(filename, db_name)

    sauvegarde_avant = creer_sauvegarde(db_name)

    path, _ = _obtenir_chemins(filename, db_name)
    blob = path.read_bytes()
    plain = dechiffrer(blob)

    with tempfile.NamedTemporaryFile(suffix=".dump") as f:
        f.write(plain)
        f.flush()

        env = os.environ.copy()
        env["PGPASSWORD"] = env.get("DB_PASSWORD", "")

        cmd = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
            "-h", env.get("DB_HOST", "postgres-erp"),
            "-p", env.get("DB_PORT", "5432"),
            "-U", env.get("DB_USER", "erp_user"),
            "-d", db_name,
            f.name,
        ]

        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=1800
        )

        if result.returncode:
            raise RuntimeError("Échec de la restauration PostgreSQL.")

    return {
        "base": db_name,
        "restauration": "terminée",
        "sauvegarde_avant_restauration": sauvegarde_avant["fichier"],
        "avertissement": (
            "Une sauvegarde chiffrée de l'état précédent a été créée "
            "automatiquement."
        ),
    }
