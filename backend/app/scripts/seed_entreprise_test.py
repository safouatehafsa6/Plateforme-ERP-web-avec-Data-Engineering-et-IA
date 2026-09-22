"""
seed_entreprise_test.py — Crée en une commande une entreprise de test
ENTIÈREMENT ACTIVÉE, avec son environnement ERP provisionné et son compte
Administrateur prêt à se connecter.

À quoi ça sert
--------------
Le parcours normal d'inscription (captcha -> OTP par email -> KYC ->
abonnement -> paiement) est indispensable en production, mais lourd à
refaire à chaque test. Ce script reproduit le résultat final de ce
parcours directement en base, pour pouvoir tester la connexion d'un
Administrateur Client, les pages Collaborateurs / Rôles & Permissions,
et le portail Utilisateurs externes (un client de démo est créé avec
une commande et une facture, pour tester tout de suite le téléchargement
PDF/QR code et le paiement en ligne).

RÉSERVÉ AU DÉVELOPPEMENT — ne jamais exécuter en production : il
court-circuite volontairement toutes les vérifications d'inscription.

Utilisation
-----------
    docker compose exec backend python3 -m app.scripts.seed_entreprise_test

Options (facultatives) :
    --nom "Societe Alpha"
    --email admin@societe-alpha.ma
    --mot-de-passe "Test1234!"

Le script est réexécutable : si l'email existe déjà, il l'indique et
n'écrase rien.
"""

import argparse
import os
import secrets
import sys
from datetime import datetime, timezone

import bcrypt
import psycopg2

from app.db import pool_central
from app.routers.entreprises import _slugifier, CGU_VERSION_ACTUELLE
from app.services.provisioning import provisionner_entreprise, indexer_compte_central

NOM_PAR_DEFAUT = "Societe Test"
EMAIL_PAR_DEFAUT = "admin@societe-test.ma"
MOT_DE_PASSE_PAR_DEFAUT = "Test1234!"


def _email_deja_utilise(email: str) -> bool:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, statut FROM entreprise WHERE email_contact = %s", (email,))
            return cur.fetchone()
    finally:
        pool_central.putconn(conn)


def creer_entreprise_test(nom: str, email: str, mot_de_passe: str) -> None:
    email = email.strip().lower()

    existante = _email_deja_utilise(email)
    if existante:
        entreprise_id, statut = existante
        print(f"Une entreprise existe déjà avec l'email {email} (id={entreprise_id}, statut={statut}).")
        print("Utilisez un autre email avec --email, ou supprimez cette entreprise avant de relancer.")
        sys.exit(1)

    identifiant_unique = secrets.token_hex(4).upper()
    nom_base = f"compte_{_slugifier(nom)}_{identifiant_unique.lower()}"
    mot_de_passe_hash = bcrypt.hashpw(mot_de_passe.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # 1. L'entreprise, directement au statut final "actif" (le parcours
    #    en_attente -> valide -> actif est court-circuité ici).
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO entreprise
                   (type_compte, nom, secteur, identifiant_unique, nom_base, statut,
                    email_contact, telephone_contact, cgu_accepte_le, cgu_version)
                   VALUES ('entreprise', %s, %s, %s, %s, 'actif', %s, %s, %s, %s)
                   RETURNING id""",
                (
                    nom, "Test", identifiant_unique, nom_base, email,
                    "0600000000", datetime.now(timezone.utc), CGU_VERSION_ACTUELLE,
                ),
            )
            entreprise_id = cur.fetchone()[0]

            # 2. Un abonnement actif : la connexion vérifie que l'entreprise
            #    est bien au statut "actif", et l'interface d'administration
            #    des abonnements attend une ligne ici.
            cur.execute(
                """INSERT INTO abonnement (entreprise_id, type_plan, statut, date_debut)
                   VALUES (%s, 'essai', 'actif', CURRENT_DATE)""",
                (entreprise_id,),
            )
        conn.commit()
    finally:
        pool_central.putconn(conn)

    # 3. Création réelle de la base dédiée, de son schéma, du compte
    #    Administrateur et de son indexation centrale (email -> entreprise).
    print(f"Provisioning de la base « {nom_base} »...")
    provisionner_entreprise(nom_base, nom, email, mot_de_passe_hash, entreprise_id)

    # 4. Client de test + compte du portail Utilisateurs externes, avec une
    #    commande et une facture, pour pouvoir tester tout de suite le
    #    téléchargement PDF/QR code et le paiement en ligne sans avoir à
    #    passer par les modules Ventes (pas encore construits).
    email_client = "client@societe-test.ma"
    mot_de_passe_client = "Client1234!"
    mot_de_passe_client_hash = bcrypt.hashpw(mot_de_passe_client.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    pool_tenant = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER", "erp_user"), password=os.getenv("DB_PASSWORD", "erp_password"),
        dbname=nom_base,
    )
    try:
        with pool_tenant.cursor() as cur:
            cur.execute(
                "INSERT INTO client (nom, email, telephone) VALUES (%s, %s, %s) RETURNING id",
                ("Client Démo", email_client, "0600000001"),
            )
            client_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO commande (client_id, statut, montant_total) VALUES (%s, 'confirmee', %s) RETURNING id",
                (client_id, 1250.00),
            )
            commande_id = cur.fetchone()[0]

            cur.execute(
                """INSERT INTO facture (commande_id, numero, montant_total, statut)
                   VALUES (%s, %s, %s, 'impayee')""",
                (commande_id, f"FAC-{identifiant_unique}-001", 1250.00),
            )

            cur.execute(
                "INSERT INTO utilisateur_externe (client_id, email, mot_de_passe, actif) VALUES (%s, %s, %s, TRUE)",
                (client_id, email_client, mot_de_passe_client_hash),
            )
        pool_tenant.commit()
    finally:
        pool_tenant.close()

    indexer_compte_central(email_client, entreprise_id, nom_base, type_compte="externe")

    print()
    print("=" * 62)
    print("ENTREPRISE DE TEST CRÉÉE ET ACTIVÉE")
    print("=" * 62)
    print(f"  Entreprise    : {nom} (id={entreprise_id}, identifiant {identifiant_unique})")
    print(f"  Base dédiée   : {nom_base}")
    print()
    print("  Connexion Administrateur Client (page de connexion habituelle) :")
    print(f"    Email       : {email}")
    print(f"    Mot de passe: {mot_de_passe}")
    print()
    print("  Connexion Portail Utilisateurs externes (compte client de démo) :")
    print(f"    Email       : {email_client}")
    print(f"    Mot de passe: {mot_de_passe_client}")
    print(f"    -> 1 commande confirmée + 1 facture impayée déjà créées pour ce client.")
    print()
    print("  Une fois connectée en Admin, la barre latérale doit afficher")
    print("  « Collaborateurs », « Rôles & Permissions » et « Utilisateurs Externes ».")
    print("=" * 62)


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description="Crée une entreprise de test activée.")
    parseur.add_argument("--nom", default=NOM_PAR_DEFAUT)
    parseur.add_argument("--email", default=EMAIL_PAR_DEFAUT)
    parseur.add_argument("--mot-de-passe", dest="mot_de_passe", default=MOT_DE_PASSE_PAR_DEFAUT)
    args = parseur.parse_args()

    creer_entreprise_test(args.nom, args.email, args.mot_de_passe)
