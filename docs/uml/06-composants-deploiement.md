# Diagramme de composants et de déploiement — Plateforme ERP SaaS

> Ce diagramme donne la vue technique globale de l'architecture, en
> cohérence avec les sections 3 (Multi-Tenant/Multi-Database), 6 (Data
> Engineering) et 13 (Cloud Computing) du cahier des charges.

## Diagramme de composants (Mermaid — s'affiche automatiquement sur GitHub)

```mermaid
flowchart TB
    subgraph CLIENT["Côté client"]
        Web[Frontend Web\nReact]
    end

    subgraph CLOUD["Infrastructure Cloud"]
        subgraph API["Backend / API"]
            Auth[Service d'authentification\n+ routage multi-tenant]
            Logique[Logique métier ERP]
            IAAssist[Assistant IA\nrecherche + OCR]
        end

        subgraph BASES["Couche données relationnelle"]
            Central[(Base centrale\nBase_Centrale.sql)]
            EntA[(Base entreprise A\nsociete_alpha.sql)]
            EntB[(Base entreprise B\nsociete_tech.sql)]
        end

        subgraph DATA["Pipeline Big Data"]
            Airflow[Apache Airflow\norchestration]
            Spark[Apache Spark\ntraitement distribué]
            MinIO[(MinIO\nData Lake - Bronze/Silver/Gold)]
            Analytics[Couche analytique\nindicateurs, tableaux de bord]
        end
    end

    subgraph EXTERNE["Services externes"]
        Paiement[Paiement en ligne\nStripe / CMI / PayPal]
        Notification[Notifications\nEmail / SMS / WhatsApp]
    end

    Web -->|HTTPS / API REST| Auth
    Auth --> Logique
    Auth -->|identifie l'entreprise| Central
    Auth -->|sélectionne et connecte| EntA
    Auth -->|sélectionne et connecte| EntB

    Logique --> IAAssist
    Logique -->|paiement| Paiement
    Logique -->|notification| Notification

    EntA -->|extraction périodique| Airflow
    EntB -->|extraction périodique| Airflow
    Airflow --> Spark
    Spark --> MinIO
    MinIO --> Analytics
    Analytics -->|indicateurs| Logique
```

## Diagramme de déploiement (vue infrastructure)

```mermaid
flowchart TB
    subgraph Utilisateur["Poste utilisateur"]
        Browser[Navigateur Web]
    end

    subgraph ServeurWeb["Serveur Web (conteneur Docker)"]
        Frontend[Frontend React\nservi via Nginx]
    end

    subgraph ServeurApp["Serveur applicatif (conteneur Docker)"]
        BackendAPI[Backend API]
    end

    subgraph ServeurDB["Serveur de bases de données"]
        PG[(PostgreSQL\nBase centrale + Bases entreprises)]
    end

    subgraph ServeurData["Cluster Data Engineering (conteneurs Docker)"]
        AirflowSrv[Airflow]
        SparkSrv[Spark]
        MinIOSrv[MinIO]
    end

    Browser -->|HTTPS| Frontend
    Frontend -->|API REST| BackendAPI
    BackendAPI -->|SQL| PG
    BackendAPI -->|déclenche DAGs| AirflowSrv
    AirflowSrv --> SparkSrv
    SparkSrv --> MinIOSrv
    PG -.->|extraction périodique| AirflowSrv
```

## Notes de modélisation

- Le **diagramme de composants** montre les modules logiques et leurs
  interactions ; le **diagramme de déploiement** montre où ces modules
  s'exécutent physiquement (conteneurs, serveurs).
- Le routage multi-tenant (Auth → Base centrale → Base entreprise) est
  représenté ici au niveau composant ; le détail pas-à-pas est dans le
  diagramme de séquence de routage réalisé par ta binôme.
- Pour un stage de 3 mois, l'architecture réelle pourra être simplifiée en
  déploiement local via **Docker Compose** (un conteneur par composant :
  frontend, backend, PostgreSQL, Airflow, Spark, MinIO), sans nécessiter de
  vraie infrastructure Cloud multi-serveurs — à mentionner explicitement
  dans le rapport comme choix pragmatique pour la durée du stage.
- Les bases par entreprise (`EntA`, `EntB`) sont représentées en exemple ;
  en réalité leur nombre est dynamique (une base créée automatiquement par
  entreprise inscrite, cf. section 3.2 du cahier des charges).
