CORRECTION ERP — NOTIFICATIONS ET RESTAURATION FRONTEND/BACKEND

Cette archive contient le projet complet basé sur l’archive fournie, avec le correctif notifications appliqué.

IMPORTANT
- L’archive ne contient pas .env ni .git : conservez votre .env local et votre dépôt Git actuel.
- Faites une copie de sauvegarde du dossier actuel avant de remplacer des fichiers.
- Décompressez le dossier du projet dans un nouvel emplacement pour vérifier le contenu avant de copier quoi que ce soit dans votre projet existant.
- Le fichier frontend/index.html est inclus comme fichier normal, pas comme dossier.

Correctifs notifications inclus
- Ajout du routeur backend des notifications et de la migration SQL 008_notifications_utilisateur.sql.
- Notification/rafraîchissement pour les actions de ventes couvertes par le correctif.
- Rafraîchissement du menu flottant de notifications.

Après avoir sauvegardé votre .env, placez les fichiers du projet à la racine attendue. Depuis cette racine :
  Get-Item .\frontend\index.html | Format-List FullName,Mode,PSIsContainer
  docker compose config --quiet
  docker compose up -d --build backend frontend
  docker compose logs --tail=100 backend frontend

La première commande doit afficher PSIsContainer : False. Ne lancez pas docker compose down -v : cela peut supprimer les volumes de données.

Note de validation : cette archive a été vérifiée structurellement et les fichiers Python modifiés ont passé py_compile. Le démarrage réel des conteneurs et la connexion à votre base locale ne peuvent pas être certifiés depuis cet environnement.
