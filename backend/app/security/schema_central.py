"""Met à niveau la base centrale d'un volume PostgreSQL DÉJÀ créé.

Les scripts de backend/database/central ne sont rejoués par l'image postgres qu'au tout premier
démarrage (volume vide). Les migrations 011 et 012 sont appliquées par appareils.py et
tentatives.py ; ce module applique les autres (010, 013, 014, 015), sinon :
  - 014 absent => la fonction consommer_connexion_essai() n'existe pas et TOUTES les connexions
    interne/externe échouent (controler_essai) ;
  - 013 absent => pas d'historique des changements de statut d'entreprise.

Chaque script n'est exécuté que s'il manque quelque chose (aucun verrou DDL inutile à chaque
démarrage) et un échec n'empêche jamais le backend de démarrer (il est journalisé).
"""
import logging
from pathlib import Path

from app.db import pool_central

_log = logging.getLogger("erp.schema_central")
_DOSSIER = Path(__file__).resolve().parents[2] / "database" / "central"

# (fichier, requête qui renvoie TRUE si la migration est déjà appliquée)
_MIGRATIONS = (
    ("010_index_sessions_expire.sql", "SELECT to_regclass('idx_session_utilisateur_expire') IS NOT NULL"),
    ("013_historique_statut_entreprise.sql",
     "SELECT to_regclass('historique_statut_entreprise') IS NOT NULL AND to_regproc('trg_historique_statut_entreprise') IS NOT NULL"),
    ("014_essai_connexions.sql",
     "SELECT to_regproc('consommer_connexion_essai') IS NOT NULL AND EXISTS (SELECT 1 FROM information_schema.columns "
     "WHERE table_name = 'abonnement' AND column_name = 'connexions_essai_max')"),
    ("015_boutons_flottants.sql",
     "SELECT to_regclass('bouton_flottant') IS NOT NULL AND to_regclass('bouton_flottant_config') IS NOT NULL "
     "AND to_regclass('bouton_flottant_historique') IS NOT NULL"),
)


def assurer_schema_central() -> list[str]:
    """Applique les migrations manquantes ; retourne la liste des fichiers appliqués."""
    appliquees = []
    for fichier, deja_appliquee in _MIGRATIONS:
        try:
            conn = pool_central.getconn()
            try:
                with conn.cursor() as cur:
                    if not (_DOSSIER / fichier).is_file():
                        conn.rollback()
                        _log.info("Migration centrale %s absente du depot : ignoree", fichier)
                        continue
                    cur.execute(deja_appliquee)
                    if cur.fetchone()[0]:
                        conn.rollback()
                        continue
                    cur.execute((_DOSSIER / fichier).read_text(encoding="utf-8"))
                conn.commit()
                appliquees.append(fichier)
                _log.info("Migration centrale appliquée : %s", fichier)
            except Exception:
                conn.rollback()
                raise
            finally:
                pool_central.putconn(conn)
        except Exception:
            _log.exception("Migration centrale %s NON appliquée (lancez-la à la main, voir docs)", fichier)
    return appliquees
