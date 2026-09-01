# Diagramme de séquence — Onboarding d'une entreprise cliente

> Diagramme 3 de la phase de conception UML. Montre comment une nouvelle
> entreprise s'inscrit sur la plateforme et obtient automatiquement son
> propre environnement ERP.

## Description du scénario

Une entreprise souhaite devenir cliente de la plateforme SaaS. Elle doit
s'inscrire, vérifier son identité (OTP puis KYC), choisir un abonnement,
payer, puis voir son environnement ERP créé automatiquement — sans
intervention manuelle du Super Administrateur pour la création technique.

## Diagramme (Mermaid — s'affiche automatiquement sur GitHub)

```mermaid
sequenceDiagram
    actor E as Représentant entreprise
    participant F as Frontend (portail d'inscription)
    participant A as API Backend
    participant BC as Base centrale
    participant OTP as Service OTP (SMS/Email)
    participant PAY as Service de paiement
    participant PROV as Service de provisioning

    E->>F: Remplit le formulaire d'inscription (nom, email, secteur)
    F->>A: POST /api/entreprises/inscription
    A->>BC: Créer l'entreprise (statut = "En attente de vérification")
    BC-->>A: entreprise_id généré
    A->>OTP: Envoyer un code OTP à l'email/téléphone fourni
    OTP-->>E: Reçoit le code OTP

    E->>F: Saisit le code OTP reçu
    F->>A: POST /api/entreprises/verifier-otp {code}
    A->>BC: Vérifier le code et mettre à jour le statut ("OTP validé")
    BC-->>A: OK

    A-->>F: Demander les documents KYC
    E->>F: Téléverse les documents (registre de commerce, ID du représentant...)
    F->>A: POST /api/entreprises/kyc {documents}
    A->>BC: Enregistrer les documents, statut = "KYC en attente de validation"
    BC-->>A: OK
    A-->>E: "Votre dossier est en cours de vérification"

    Note over A,BC: Validation manuelle ou semi-automatique du KYC<br/>par le Super Administrateur SaaS

    A->>BC: Mettre à jour statut = "KYC validé"

    E->>F: Choisit un plan d'abonnement
    F->>A: POST /api/abonnements/choisir {plan}
    A->>BC: Enregistrer le choix d'abonnement (statut = "En attente de paiement")

    E->>F: Procède au paiement
    F->>PAY: Initier le paiement sécurisé
    PAY-->>F: Confirmation de paiement

    alt Paiement échoué
        F-->>E: "Le paiement a échoué, veuillez réessayer"
    else Paiement réussi
        F->>A: POST /api/abonnements/confirmer-paiement
        A->>BC: Mettre à jour statut = "Actif", date de début d'abonnement
        A->>PROV: Provisionner l'environnement ERP (entreprise_id)
        PROV->>PROV: Créer une base dédiée (ex: societe_alpha.sql)
        PROV->>PROV: Créer les tables et données initiales
        PROV->>BC: Enregistrer les infos de connexion (nom_base, identifiant unique)
        BC-->>A: Environnement créé
        A-->>F: 200 OK "Votre environnement ERP est prêt"
        F-->>E: Redirection vers la création du compte Administrateur
    end
```

## Points clés à expliquer en soutenance

1. **Chaque étape met à jour un statut dans la base centrale** —
   ce statut pilote le diagramme d'états-transitions (diagramme suivant).
2. **Le provisioning est automatique** : dès le paiement confirmé, la base
   dédiée à l'entreprise est créée sans intervention humaine, exactement
   comme demandé dans le cahier des charges.
3. **La vérification KYC peut être manuelle** dans une première version
   simple (le Super Admin valide depuis un tableau de bord), et automatisée
   plus tard si le temps le permet.
4. **Le mode Trial** peut être modélisé comme une variante : l'entreprise
   passe directement de "KYC validé" à "Actif (essai)" sans passer par le
   paiement, avec une date d'expiration d'essai enregistrée dans la base
   centrale.

## Lien avec le diagramme suivant

Les statuts mentionnés ici (`En attente de vérification`, `OTP validé`,
`KYC en attente`, `KYC validé`, `En attente de paiement`, `Actif`,
`Suspendu`...) seront repris et complétés dans le **diagramme
d'états-transitions du cycle de vie du compte entreprise**
(`docs/uml/03-etats-cycle-de-vie-entreprise.md`).
