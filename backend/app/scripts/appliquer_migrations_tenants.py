"""
appliquer_migrations_tenants.py — Applique automatiquement, sur TOUTES les
bases entreprise existantes, les scripts de migration présents dans
backend/database/tenant-template/, en ne rejouant jamais un script déjà
appliqué sur une base donnée.

Répond directement à la remarque de l'entreprise : "il faut prévoir un
mécanisme permettant d'appliquer les évolutions de structure à l'ensemble
des bases Tenant, et pas uniquement à la base entreprise utilisée lors du
test."

Utilisation (depuis l'intérieur du conteneur backend) :

    docker compose exec backend python -m app.scripts.appliquer_migrations_tenants

Fonctionnement :
1. Récupère la liste de toutes les entreprises (et leur nom_base) depuis
   la base centrale.
2. Pour chaque base entreprise, crée (si besoin) une table de suivi
   `_migrations_appliquees` qui mémorise quels fichiers ont déjà été joués.
3. Parcourt les fichiers .sql de database/tenant-template/ dans l'ordre
   numérique (001_, 002_, 003_...) et exécute uniquement ceux qui ne sont
   pas encore dans la table de suivi de cette base précise.
4. Affiche un résumé clair de ce qui a été appliqué, base par base.
"""

import os
import re
import psycopg2

from app.db import pool_central, get_pool_entreprise

DOSSIER_MIGRATIONS_TENANT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "database", "tenant-template",
)


def _lister_fichiers_migration() -> list[str]:
    """Retourne les fichiers .sql du dossier tenant-template, triés par
    leur préfixe numérique (001_, 002_...), dans l'ordre d'application."""
    fichiers = [f for f in os.listdir(DOSSIER_MIGRATIONS_TENANT) if f.endswith(".sql")]

    def cle_tri(nom_fichier):
        m = re.match(r"^(\d+)_", nom_fichier)
        return int(m.group(1)) if m else 999999

    return sorted(fichiers, key=cle_tri)


def _table_suivi_existe(cur) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '_migrations_appliquees')"
    )
    return cur.fetchone()[0]


def _creer_table_suivi_si_absente(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations_appliquees (
            nom_fichier VARCHAR(255) PRIMARY KEY,
            date_application TIMESTAMP DEFAULT NOW()
        )
        """
    )


def _migrations_deja_appliquees(cur) -> set[str]:
    cur.execute("SELECT nom_fichier FROM _migrations_appliquees")
    return {row[0] for row in cur.fetchall()}


def appliquer_migrations_sur_toutes_les_entreprises():
    fichiers_migration = _lister_fichiers_migration()
    print(f"Fichiers de migration trouvés ({len(fichiers_migration)}) : {fichiers_migration}\n")

    conn_centrale = pool_central.getconn()
    try:
        with conn_centrale.cursor() as cur:
            cur.execute("SELECT id, nom, nom_base FROM entreprise ORDER BY id")
            entreprises = cur.fetchall()
    finally:
        pool_central.putconn(conn_centrale)

    print(f"{len(entreprises)} entreprise(s) trouvée(s).\n")

    for entreprise_id, nom, nom_base in entreprises:
        print(f"--- Entreprise #{entreprise_id} ({nom}) — base {nom_base} ---")
        try:
            pool_tenant = get_pool_entreprise(nom_base)
            conn = pool_tenant.getconn()
        except Exception as e:
            print(f"  [IGNORÉE] Impossible de se connecter à la base '{nom_base}' "
                  f"(probablement une entreprise orpheline, provisioning incomplet) : {e}\n")
            continue

        try:
            with conn.cursor() as cur:
                _creer_table_suivi_si_absente(cur)
            conn.commit()

            with conn.cursor() as cur:
                deja_appliquees = _migrations_deja_appliquees(cur)

            for nom_fichier in fichiers_migration:
                if nom_fichier in deja_appliquees:
                    print(f"  [ignoré] {nom_fichier} (déjà appliqué)")
                    continue

                chemin_complet = os.path.join(DOSSIER_MIGRATIONS_TENANT, nom_fichier)
                with open(chemin_complet, "r", encoding="utf-8") as f:
                    script_sql = f.read()

                try:
                    with conn.cursor() as cur:
                        cur.execute(script_sql)
                        cur.execute(
                            "INSERT INTO _migrations_appliquees (nom_fichier) VALUES (%s)",
                            (nom_fichier,),
                        )
                    conn.commit()
                    print(f"  [appliqué]  {nom_fichier}")
                except Exception as e:
                    conn.rollback()
                    print(f"  [ERREUR]   {nom_fichier} -> {e}")
        finally:
            pool_tenant.putconn(conn)

        print()

    print("Terminé.")


if __name__ == "__main__":
    appliquer_migrations_sur_toutes_les_entreprises()
