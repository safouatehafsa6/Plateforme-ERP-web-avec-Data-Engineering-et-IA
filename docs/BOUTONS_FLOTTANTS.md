# Boutons flottants administrables

**Où ?** Menu « Boutons flottants » (Super Administrateur) → `/admin/boutons-flottants`.
Configuration au niveau **plateforme** (base centrale) : elle s'applique à tous les écrans, publics et connectés.

## Ce que l'administrateur peut faire (sans toucher au code)
- Ajouter, modifier, activer/désactiver, supprimer des boutons (les 8 boutons d'origine ne se suppriment pas, ils se désactivent ; « Restaurer » les remet à zéro).
- Titres en français / anglais / arabe, icône (34 au choix), couleur, taille, ordre (flèches haut/bas).
- Emplacement : dans le menu d'aide, ou bouton isolé à l'un des 6 coins/bords de l'écran.
- Action : assistant IA, notifications, support, thème, langue, page interne, lien externe (https, mailto, tel), WhatsApp.
- Conditions : visiteurs / connectés, profils (super admin, admin d'entreprise, interne, externe), mobile / ordinateur, pages incluses / exclues, période d'affichage.
- Réglages du bouton principal : position, taille, couleur, icône, activation globale.
- Historique des modifications (qui, quand, quoi).

## Sécurité
- Écriture réservée au Super Admin (API) ; lecture publique (c'est de l'affichage).
- Liens validés côté API **et** par contraintes SQL : `javascript:`, `http://`, `//evil`, couleurs ou icônes inconnues sont refusés.
- Si l'API est injoignable, le menu d'aide d'origine s'affiche (aucune perte de fonction).

## API
`GET /api/boutons-flottants` (public) · `GET/POST /api/admin/boutons-flottants` · `PUT/DELETE /api/admin/boutons-flottants/{id}` ·
`PATCH …/{id}/actif` · `PUT …/ordre` · `PUT …/config` · `POST …/restaurer` · `GET …/historique`

## Mise en route
La migration `015_boutons_flottants.sql` est appliquée automatiquement au démarrage du backend (`schema_central.py`).
```bash
docker compose up -d --build
docker compose logs backend | grep -i "migration centrale"
```
