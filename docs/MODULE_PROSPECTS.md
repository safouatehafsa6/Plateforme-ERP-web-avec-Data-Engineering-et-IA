# Module Prospects & suivi commercial

## Mise en route

Nouvelle entreprise : rien à faire (le provisioning applique `019` et `020`).
Entreprises existantes, une seule fois (idempotent) :

```bash
cd backend
python -m app.scripts.migrate_prospects
```

Tests :

```bash
cd backend  && python -m unittest discover -s tests          # tests_prospects_api : nécessite PostgreSQL (DB_* comme l'appli), sinon ignoré
cd frontend && npm test
```

## Fonctionnement

| Exigence | Implémentation |
|---|---|
| Création / gestion | `POST/PATCH /api/prospects`, page `/prospects`. Nom + (e-mail ou téléphone) obligatoires. |
| Vérification & doublons | Contrôle en direct (`/verification-doublon`) puis à l'enregistrement, parmi prospects **et** clients. **Fort** (même e-mail / téléphone — 8 derniers chiffres, donc `+216 12 345 678` = `12345678`) : bloquant. **Possible** (nom identique ou proche, sans accents ni SARL/STE) : à confirmer. Index uniques en base contre les accès concurrents. |
| Conversion | `POST /{id}/convertir` : crée le client (transaction + verrou), ou le rattache à un client existant (`client_existant_id`). Bloquée si doublon client, prospect archivé, perdu ou déjà converti. |
| Suivi daté | Table `suivi_commercial`, **en ajout seul** (trigger SQL interdisant UPDATE/DELETE). Chaque création, modification (champs avant/après), changement de statut, conversion, archivage, réactivation et chaque suivi manuel (appel, e-mail, rendez-vous, note, relance) y est daté et signé. Date passée autorisée, future refusée. Relance planifiée + alerte de retard. |
| Permissions | RBAC existant, module `prospects` (voir tableau ci-dessous). Appliqué côté API **et** reflété dans l'interface. |
| Archivage / réactivation | Logique (`archive`, motif, auteur, date). Aucune suppression ; l'historique reste lisible ; fiche archivée en lecture seule ; son e-mail/téléphone reste réservé. Même mécanisme pour les clients (refusé s'il reste une commande `en_cours`/`confirmee` ou un devis `brouillon`/`envoye`) ; les clients archivés disparaissent des nouveaux devis/commandes mais pas des anciens. |

## Permissions

| Opération | Prospects | Clients |
|---|---|---|
| Consulter (liste, fiche, historique) | `prospects.consulter` | `clients.consulter` |
| Créer / ajouter un suivi | `prospects.creer` | `clients.modifier` (suivi) |
| Modifier, changer le statut | `prospects.modifier` | `clients.modifier` |
| Convertir en client | `prospects.valider` | — |
| Archiver / réactiver | `prospects.supprimer` | `clients.supprimer` |

Par défaut : `Admin` et `Responsable Commercial` ont tous les droits prospects ; seul `Admin` peut archiver un client.
Tout reste modifiable dans « Rôles & Permissions ».

## Workflow des statuts

`nouveau → contacté → qualifié → converti` ; `perdu` (motif obligatoire) peut être rouvert (`nouveau`/`contacté`).
`converti` n'est atteint que par la conversion.
