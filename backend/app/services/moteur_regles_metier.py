
"""Registre extensible de règles métier et calcul des documents commerciaux.

Les taux sont lus dans le référentiel de chaque entreprise. Aucun taux fiscal
légal n'est présumé : la TVA par défaut est initialisée à 0 % et doit être
configurée par l'administrateur selon le régime applicable.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Any
import json


CENT = Decimal("0.01")


def D(v: Any) -> Decimal:
    """Convertit une valeur en Decimal sans introduire d'erreur float."""
    return Decimal(str(v if v is not None else 0))


def money(v: Any) -> Decimal:
    """Arrondit un montant à deux décimales."""
    return D(v).quantize(CENT, rounding=ROUND_HALF_UP)


def charger_taux(
    cur,
    code: str,
    taux_defaut="0",
    module="general",
) -> Decimal:
    """Charge la règle du module, sinon la règle générale.

    Une règle spécifique au module est prioritaire sur une règle générale.
    La priorité et l'identifiant départagent les règles d'un même niveau.
    """
    cur.execute(
        """
        SELECT taux
        FROM regle_calcul_metier
        WHERE code = %s
          AND actif = TRUE
          AND module_source IN (%s, 'general')
          AND (date_debut IS NULL OR date_debut <= CURRENT_DATE)
          AND (date_fin IS NULL OR date_fin >= CURRENT_DATE)
        ORDER BY
          (module_source = %s) DESC,
          priorite DESC,
          id DESC
        LIMIT 1
        """,
        (code, module, module),
    )

    row = cur.fetchone()
    return D(row[0]) if row else D(taux_defaut)


def calculer_document(
    cur,
    *,
    module: str,
    type_document: str,
    document_id: int,
    lignes: list[dict],
    auteur: str,
    reference: str | None = None,
):
    """Calcule HT/remise/TVA/TTC, fige les détails et enregistre les anomalies."""

    # Règles du module avec repli sur les règles générales.
    taux_defaut = charger_taux(
        cur,
        "TVA_DEFAUT",
        "0",
        module,
    )

    remise_defaut = charger_taux(
        cur,
        "REMISE_DEFAUT",
        "0",
        module,
    )

    if taux_defaut < 0 or taux_defaut > 100:
        raise ValueError(
            "Le taux TVA_DEFAUT doit être compris entre 0 et 100 %."
        )

    if remise_defaut < 0 or remise_defaut > 100:
        raise ValueError(
            "Le taux REMISE_DEFAUT doit être compris entre 0 et 100 %."
        )

    ht_brut = Decimal("0")
    remise_total = Decimal("0")
    ht = Decimal("0")
    tva = Decimal("0")

    details = []
    anomalies = []

    for ligne in lignes:
        q = int(ligne.get("quantite") or 0)
        pu = D(ligne.get("prix_unitaire"))

        # Si la ligne ne précise pas de remise, appliquer la remise par défaut.
        remise_valeur = ligne.get("remise_pct")
        remise_pct = (
            D(remise_valeur)
            if remise_valeur is not None
            else remise_defaut
        )

        taux_tva = (
            D(ligne.get("taux_tva"))
            if ligne.get("taux_tva") is not None
            else taux_defaut
        )

        if (
            q <= 0
            or pu < 0
            or remise_pct < 0
            or remise_pct > 100
            or taux_tva < 0
            or taux_tva > 100
        ):
            raise ValueError(
                "Une ligne contient une quantité, un prix ou un taux invalide."
            )

        brut = money(pu * q)
        remise = money(brut * remise_pct / Decimal("100"))
        net = money(brut - remise)
        taxe = money(net * taux_tva / Decimal("100"))
        total = money(net + taxe)

        ht_brut += brut
        remise_total += remise
        ht += net
        tva += taxe

        if remise_pct >= 50:
            anomalies.append({
                "code": "REMISE_ELEVEE",
                "gravite": "attention",
                "message": (
                    f"Remise élevée ({remise_pct} %) sur une ligne."
                ),
            })

        if taux_tva > 25:
            anomalies.append({
                "code": "TVA_ATYPIQUE",
                "gravite": "attention",
                "message": (
                    f"Taux TVA inhabituel ({taux_tva} %). "
                    "Vérifier le paramétrage."
                ),
            })

        details.append({
            "produit_id": ligne.get("produit_id"),
            "designation": ligne.get("designation"),
            "quantite": q,
            "prix_unitaire": str(pu),
            "remise_pct": str(remise_pct),
            "taux_tva": str(taux_tva),
            "montant_brut": str(brut),
            "remise": str(remise),
            "montant_ht": str(net),
            "montant_tva": str(taxe),
            "montant_ttc": str(total),
        })

    ht_brut = money(ht_brut)
    remise_total = money(remise_total)
    ht = money(ht)
    tva = money(tva)
    ttc = money(ht + tva)

    snapshot = {
        "version": 2,
        "module": module,
        "type_document": type_document,
        "reference": reference,
        "devise": "MAD",
        "date_calcul": date.today().isoformat(),
        "montant_brut": str(ht_brut),
        "remise_totale": str(remise_total),
        "montant_ht": str(ht),
        "montant_tva": str(tva),
        "montant_ttc": str(ttc),
        "taux_tva_defaut": str(taux_defaut),
        "remise_defaut": str(remise_defaut),
        "lignes": details,
    }

    # Historique : un seul enregistrement par document, mis à jour au recalcul.
    cur.execute(
        """
        INSERT INTO historique_calcul_metier
            (
                module_source,
                type_document,
                document_id,
                reference,
                montant_ht,
                montant_tva,
                montant_ttc,
                details,
                cree_par
            )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (module_source, type_document, document_id)
        DO UPDATE SET
            reference = EXCLUDED.reference,
            montant_ht = EXCLUDED.montant_ht,
            montant_tva = EXCLUDED.montant_tva,
            montant_ttc = EXCLUDED.montant_ttc,
            details = EXCLUDED.details,
            cree_par = EXCLUDED.cree_par,
            cree_le = NOW()
        """,
        (
            module,
            type_document,
            document_id,
            reference,
            ht,
            tva,
            ttc,
            json.dumps(snapshot, ensure_ascii=False),
            str(auteur),
        ),
    )

    # Anomalies : nécessite l'index unique ajouté dans la migration 021.
    for anomalie in anomalies:
        cur.execute(
            """
            INSERT INTO anomalie_calcul_metier
                (
                    module_source,
                    type_document,
                    document_id,
                    code,
                    gravite,
                    message,
                    details
                )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (
                module_source,
                type_document,
                document_id,
                code
            )
            DO UPDATE SET
                gravite = EXCLUDED.gravite,
                message = EXCLUDED.message,
                details = EXCLUDED.details,
                cree_le = NOW()
            WHERE anomalie_calcul_metier.statut = 'nouvelle'
            """,
            (
                module,
                type_document,
                document_id,
                anomalie["code"],
                anomalie["gravite"],
                anomalie["message"],
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )

    return {
        "montant_brut": ht_brut,
        "remise_totale": remise_total,
        "montant_ht": ht,
        "montant_tva": tva,
        "montant_ttc": ttc,
        "details": snapshot,
        "anomalies": anomalies,
    }


_SCHEMA_PRET: set[str] = set()


def assurer_schema(pool, nom_base: str):
    """Applique une seule fois la migration 021 par base et par processus."""
    if nom_base in _SCHEMA_PRET:
        return

    from pathlib import Path

    fichier = (
        Path(__file__).resolve().parents[2]
        / "database"
        / "tenant-template"
        / "021_moteur_regles_metier.sql"
    )

    script = fichier.read_text(encoding="utf-8")

    conn = pool.getconn()

    try:
        with conn.cursor() as cur:
            cur.execute(script)

        conn.commit()
        _SCHEMA_PRET.add(nom_base)

    except Exception:
        conn.rollback()
        raise

    finally:
        pool.putconn(conn)


def calculer_penalite_retard(
    cur,
    montant_impaye,
    date_echeance,
    date_calcul=None,
):
    """Pénalité simple annualisée : impayé × taux annuel × jours/365."""

    date_calcul = date_calcul or date.today()

    if not date_echeance:
        raise ValueError(
            "La date d'échéance de la facture n'est pas renseignée."
        )

    jours = max(0, (date_calcul - date_echeance).days)

    taux = charger_taux(
        cur,
        "PENALITE_RETARD",
        "0",
        "ventes",
    )

    if taux < 0 or taux > 100:
        raise ValueError(
            "Le taux PENALITE_RETARD doit être compris entre 0 et 100 %."
        )

    montant = D(montant_impaye)

    if montant < 0:
        raise ValueError(
            "Le montant impayé ne peut pas être négatif."
        )

    penalite = money(
        montant
        * taux
        / Decimal("100")
        * Decimal(jours)
        / Decimal("365")
    )

    return {
        "montant_impaye": money(montant),
        "taux_annuel": taux,
        "jours_retard": jours,
        "penalite": penalite,
    }
