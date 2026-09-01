# Diagramme d'activité — Automatisation documentaire par IA (OCR)

> Ce diagramme détaille le processus d'automatisation documentaire décrit en
> section 7 du cahier des charges : extraction intelligente d'informations
> à partir d'un document (ex. facture fournisseur), avec validation humaine
> avant intégration dans l'ERP.

## Flux général

```
Document → OCR → Extraction intelligente → Contrôle → Validation
(utilisateur) → Intégration ERP
```

## Diagramme (Mermaid — s'affiche automatiquement sur GitHub)

```mermaid
flowchart TD
    Start([Début]) --> Upload[Utilisateur dépose un document\nex: facture fournisseur]
    Upload --> Format{Format supporté ?}
    Format -- Non --> ErreurFormat[Afficher erreur\nformat non supporté]
    ErreurFormat --> End1([Fin])

    Format -- Oui --> OCR[Lancer l'OCR\nnumérisation du texte]
    OCR --> Extraction[Extraction intelligente des champs\nfournisseur, date, montant, TVA, références]

    Extraction --> Qualite{Extraction jugée fiable ?}
    Qualite -- Non --> Manuel[Signaler les champs incertains\npour saisie manuelle]
    Manuel --> Revue

    Qualite -- Oui --> Revue[Afficher les données extraites\nà l'utilisateur pour vérification]

    Revue --> Decision{Utilisateur valide ?}
    Decision -- Corrige des champs --> Correction[Utilisateur modifie\nles champs incorrects]
    Correction --> Revue

    Decision -- Rejette le document --> Rejet[Document marqué comme rejeté]
    Rejet --> End2([Fin])

    Decision -- Valide --> Controle[Contrôle de cohérence\nex: montant TTC = HT + TVA]
    Controle --> ControleOK{Cohérent ?}
    ControleOK -- Non --> Revue
    ControleOK -- Oui --> Integration[Intégration dans l'ERP\ncréation Facture/Document lié]

    Integration --> Notif[Notifier l'utilisateur\nintégration réussie]
    Notif --> End3([Fin])
```

## Notes de modélisation

- **La validation humaine reste obligatoire avant toute intégration** dans
  l'ERP, conformément à la section 7 du cahier des charges ("la validation
  finale est effectuée par l'utilisateur avant intégration").
- Le contrôle de cohérence (ex. vérifier que le montant TTC correspond bien
  au HT + TVA extraits) est une étape de sécurité pour éviter d'intégrer des
  données erronées issues d'une mauvaise lecture OCR.
- Ce flux s'applique en priorité aux **factures fournisseurs**, mais peut
  être réutilisé pour d'autres documents entrants (bons de livraison,
  bons de réception) en adaptant les champs extraits.
- L'étape "Extraction intelligente" correspond à l'appel à l'assistant IA
  mentionné comme acteur secondaire dans le diagramme de cas d'utilisation
  (`01-diagramme-cas-utilisation.md`, cas "Extraire un document (OCR)").
- Ce diagramme reste au niveau processus métier ; le détail technique de
  l'appel à l'API IA d'OCR (ex. requête/réponse) pourra être précisé dans
  un diagramme de séquence complémentaire si nécessaire.

## Prochaine étape

Diagramme de composants / déploiement (`docs/uml/06-composants-deploiement.md`) :
vue technique globale de l'architecture (Frontend, Backend/API, Base
centrale, Bases entreprises, Airflow, Spark, MinIO, Assistant IA,
déploiement Cloud).
