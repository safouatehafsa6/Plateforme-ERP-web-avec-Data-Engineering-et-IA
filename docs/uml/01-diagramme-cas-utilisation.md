# Diagramme de cas d'utilisation — Plateforme ERP intelligente

## Acteurs

| Acteur | Description |
|---|---|
| **Administrateur** | Gère les utilisateurs, les rôles, la configuration multilingue du système |
| **Employé** | Utilise les modules métier au quotidien (stocks, achats, ventes) |
| **Manager** | Valide les opérations, consulte les tableaux de bord décisionnels |
| **Client** | Passe des commandes, paie en ligne, échange avec l'assistant IA |
| **Système de notification** *(acteur secondaire)* | Envoie les notifications multicanales déclenchées par l'ERP |

## Diagramme (Mermaid — s'affiche automatiquement sur GitHub)

```mermaid
flowchart LR
    Admin([Administrateur])
    Employe([Employé])
    Manager([Manager])
    Client([Client])
    Notif([Système de notification])

    subgraph SYS["Système ERP"]
        UC1(("S'authentifier"))
        UC2(("Gérer utilisateurs et rôles"))
        UC3(("Gérer les stocks"))
        UC4(("Gérer achats / ventes"))
        UC5(("Passer une commande"))
        UC6(("Générer une facture électronique"))
        UC7(("Effectuer un paiement en ligne"))
        UC8(("Consulter tableaux de bord"))
        UC9(("Interagir avec l'assistant IA"))
        UC10(("Recevoir une notification"))
    end

    Admin --> UC1
    Admin --> UC2
    Employe --> UC1
    Employe --> UC3
    Employe --> UC4
    Manager --> UC1
    Manager --> UC8
    Manager --> UC4
    Client --> UC1
    Client --> UC5
    Client --> UC7
    Client --> UC9
    UC5 --> UC6
    UC6 --> UC7
    UC5 -.-> UC10
    UC7 -.-> UC10
    Notif --> UC10
```

## Notes de modélisation

- Les traits pleins représentent une association acteur → cas d'utilisation.
- Les traits pointillés représentent une relation `<<include>>` implicite
  (ex : passer une commande déclenche une notification).
- Ce diagramme est volontairement synthétique. Chaque module (stocks, achats,
  ventes, RH, comptabilité...) pourra être détaillé dans un diagramme de cas
  d'utilisation plus fin dans un fichier séparé au fur et à mesure de
  l'avancement (`02-cas-utilisation-stocks.md`, etc.).
- Prochaine étape : diagramme de classes (`docs/uml/03-diagramme-classes.md`),
  qui traduira chaque cas d'utilisation en entités et relations, base directe
  du modèle de données (`docs/mcd`).

## Répartition suggérée pour le binôme

- **Membre A** : cas d'utilisation liés à l'ERP cœur (authentification,
  utilisateurs, stocks, achats/ventes, facturation, paiement).
- **Membre B** : cas d'utilisation liés à la donnée et aux services avancés
  (tableaux de bord, assistant IA, notifications).

Les deux doivent valider ensemble ce diagramme avant de passer au diagramme
de classes, car les deux volets partagent les mêmes entités de base
(Utilisateur, Commande, Produit...).
