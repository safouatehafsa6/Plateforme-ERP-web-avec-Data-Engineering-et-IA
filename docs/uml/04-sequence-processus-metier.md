# Diagrammes de séquence — Processus métier ERP

> Ces diagrammes détaillent, dans le temps, les échanges entre acteurs et
> composants du système pour les deux processus métier de référence décrits
> en section 5 du cahier des charges. Ils s'appuient directement sur les
> classes définies dans `03-diagramme-classes.md`.

## 1. Processus de vente : Client → Devis → Commande → Facture → Paiement

```mermaid
sequenceDiagram
    actor Client
    participant ERP as Interface ERP
    participant Backend as Backend API
    participant DB as Base entreprise
    participant Paiement as Service de paiement
    participant Notif as Système de notification

    Client->>ERP: Demande un devis
    ERP->>Backend: Créer Devis
    Backend->>DB: Enregistrer Devis (statut: en attente)
    DB-->>Backend: Devis créé
    Backend-->>ERP: Confirmation
    ERP-->>Client: Devis envoyé

    Client->>ERP: Valide le devis (transforme en commande)
    ERP->>Backend: Créer Commande à partir du Devis
    Backend->>DB: Vérifier disponibilité stock
    DB-->>Backend: Stock disponible
    Backend->>DB: Enregistrer Commande + LignesCommande
    DB-->>Backend: Commande créée
    Backend-->>ERP: Confirmation commande
    ERP-->>Client: Commande confirmée

    Backend->>DB: Générer Facture liée à la Commande
    DB-->>Backend: Facture créée (statut: impayée)
    Backend-->>ERP: Facture disponible

    Client->>ERP: Effectue le paiement
    ERP->>Backend: Initier Paiement
    Backend->>Paiement: Demande de transaction (Stripe/CMI/PayPal)
    Paiement-->>Backend: Confirmation transaction
    Backend->>DB: Enregistrer Paiement + mettre à jour statut Facture
    DB-->>Backend: Facture soldée
    Backend->>Notif: Déclencher notification
    Notif-->>Client: Notification (facture payée)
    Backend-->>ERP: Paiement confirmé
    ERP-->>Client: Confirmation finale
```

## 2. Processus d'achat : Fournisseur → Achat → Réception → Stock → Facturation

```mermaid
sequenceDiagram
    actor Utilisateur as Utilisateur métier (Achats)
    participant ERP as Interface ERP
    participant Backend as Backend API
    participant DB as Base entreprise
    actor Fournisseur

    Utilisateur->>ERP: Crée une commande d'achat
    ERP->>Backend: Enregistrer commande d'achat
    Backend->>DB: Sauvegarder Commande fournisseur
    DB-->>Backend: Commande enregistrée
    Backend-->>ERP: Confirmation
    ERP-->>Fournisseur: Envoi du bon de commande

    Fournisseur-->>Utilisateur: Livraison des produits
    Utilisateur->>ERP: Enregistre la réception
    ERP->>Backend: Créer Réception liée à la commande
    Backend->>DB: Vérifier quantités reçues vs commandées
    DB-->>Backend: Écart validé ou signalé

    Backend->>DB: Mettre à jour Stock (quantités reçues)
    DB-->>Backend: Stock mis à jour
    Backend-->>ERP: Réception confirmée
    ERP-->>Utilisateur: Stock actualisé

    Fournisseur->>ERP: Envoi de la facture fournisseur
    ERP->>Backend: Enregistrer Facture fournisseur
    Backend->>DB: Associer Facture à la Commande/Réception
    DB-->>Backend: Facture enregistrée (statut: à payer)
    Backend-->>ERP: Confirmation
    ERP-->>Utilisateur: Facture fournisseur disponible pour paiement
```

## Notes de modélisation

- Les deux séquences se déroulent **entièrement à l'intérieur d'une base
  entreprise** : le routage multi-tenant (sélection de la bonne base après
  authentification) est déjà traité dans le diagramme de séquence dédié de
  ton amie et n'est pas répété ici.
- Le processus de vente inclut le service de paiement externe et le système
  de notification, conformément au flux détaillé dans
  `01-diagramme-cas-utilisation.md`.
- Le processus d'achat reste volontairement simple (pas de gestion des
  litiges ou des avoirs fournisseurs) pour rester lisible ; ces cas
  pourront être mentionnés comme extensions possibles dans le rapport final.
- Les deux diagrammes réutilisent exactement les classes définies dans
  `03-diagramme-classes.md` (Devis, Commande, LigneCommande, Facture,
  Paiement, Produit, Stock, Fournisseur).

## Prochaine étape

Diagramme d'activité de l'automatisation documentaire par IA/OCR
(`docs/uml/05-activite-ocr.md`) : `Document → OCR → Extraction intelligente
→ Contrôle → Validation utilisateur → Intégration ERP`.
