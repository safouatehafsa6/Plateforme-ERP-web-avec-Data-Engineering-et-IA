# Diagramme de classes — Plateforme ERP SaaS intelligente

> Ce diagramme traduit les cas d'utilisation (`01-diagramme-cas-utilisation.md`)
> en entités et relations, en respectant le découpage en deux bases imposé
> par l'architecture Multi-Tenant / Multi-Database (voir cahier des charges,
> section 3).

## Principe de séparation

Le modèle est découpé en **deux groupes de classes**, correspondant aux deux
bases de données réelles du système :

- **Base centrale** (`Base_Centrale.sql`) — gère la plateforme SaaS elle-même
  (entreprises clientes, abonnements, sécurité globale).
- **Base entreprise** (`societe_xxx.sql`) — une base indépendante par
  entreprise cliente, contenant toutes les données métier de son ERP.

Il n'y a **aucune clé étrangère directe en base** entre les deux : le seul
lien logique est `Entreprise.nomBaseDediee`, résolu au moment du routage
dynamique après authentification (cf. diagramme de séquence dédié).

## Diagramme (Mermaid — s'affiche automatiquement sur GitHub)

```mermaid
classDiagram
    %% ===================== BASE CENTRALE (Plateforme SaaS) =====================
    class SuperAdministrateur {
        +id
        +nom
        +email
        +motDePasseHash
        +dateCreation
    }

    class Entreprise {
        +id
        +nom
        +identifiantUnique
        +statut
        +dateInscription
        +dateActivation
        +nomBaseDediee
    }

    class Abonnement {
        +id
        +type
        +dateDebut
        +dateFin
        +statut
    }

    class Licence {
        +id
        +type
        +dateExpiration
    }

    class PeriodeEssai {
        +id
        +dateDebut
        +dateFin
        +conditionsUtilisation
    }

    class JournalAudit {
        +id
        +action
        +auteur
        +dateAction
        +details
    }

    class ParametreGlobal {
        +id
        +cle
        +valeur
    }

    SuperAdministrateur "1" --> "*" Entreprise : supervise
    Entreprise "1" --> "0..1" Abonnement : possède
    Entreprise "1" --> "0..1" Licence : possède
    Entreprise "1" --> "0..1" PeriodeEssai : bénéficie
    SuperAdministrateur "1" --> "*" JournalAudit : consulte

    %% ===================== BASE ENTREPRISE (Environnement ERP dédié) =====================
    class Utilisateur {
        +id
        +nom
        +email
        +motDePasseHash
        +statut
    }

    class Role {
        +id
        +nom
    }

    class Permission {
        +id
        +module
        +action
    }

    class Departement {
        +id
        +nom
    }

    class Client {
        +id
        +nom
        +email
        +adresse
    }

    class Fournisseur {
        +id
        +nom
        +email
        +adresse
    }

    class Produit {
        +id
        +reference
        +nom
        +prixUnitaire
        +quantiteStock
    }

    class Devis {
        +id
        +dateCreation
        +statut
        +montantTotal
    }

    class Commande {
        +id
        +dateCommande
        +statut
        +montantTotal
    }

    class LigneCommande {
        +id
        +quantite
        +prixUnitaire
    }

    class Facture {
        +id
        +numero
        +dateEmission
        +montantTTC
        +statutPaiement
    }

    class Paiement {
        +id
        +montant
        +methode
        +dateReglement
        +statut
    }

    class Stock {
        +id
        +quantiteDisponible
        +seuilAlerte
    }

    Utilisateur "*" --> "1" Role : possède
    Role "1" --> "*" Permission : regroupe
    Utilisateur "*" --> "0..1" Departement : appartient

    Client "1" --> "*" Devis : demande
    Devis "1" --> "0..1" Commande : se transforme en
    Commande "1" --> "*" LigneCommande : contient
    LigneCommande "*" --> "1" Produit : concerne
    Commande "1" --> "0..1" Facture : génère
    Facture "1" --> "*" Paiement : encaisse
    Produit "1" --> "1" Stock : suivi par
    Fournisseur "1" --> "*" Produit : fournit
```

## Notes de modélisation

- **Séparation stricte des deux bases** : les classes du haut
  (`SuperAdministrateur`, `Entreprise`, `Abonnement`, `Licence`,
  `PeriodeEssai`, `JournalAudit`, `ParametreGlobal`) vivent dans
  `Base_Centrale.sql`. Toutes les autres classes vivent dans la base dédiée
  de chaque entreprise (`societe_xxx.sql`).
- Les entités **métier** (Client, Fournisseur, Produit, Commande...) ne sont
  pas des utilisateurs du système, conformément à la section 2 du cahier des
  charges.
- Le processus `Devis → Commande → Facture → Paiement` correspond au flux
  métier documenté en section 5 du cahier des charges.
- Simplification volontaire : les entités liées à la comptabilité, RH et
  gestion documentaire avancée (bons de livraison, écritures comptables,
  etc.) ne sont pas détaillées ici pour rester lisible — mentionnées comme
  extensions possibles plutôt qu'ajoutées intégralement.

## Prochaine étape

Diagrammes de séquence des processus métier ERP
(`docs/uml/04-sequence-processus-metier.md`) : `Client → Devis → Commande →
Facture → Paiement` et `Fournisseur → Achat → Réception → Stock →
Facturation`.
