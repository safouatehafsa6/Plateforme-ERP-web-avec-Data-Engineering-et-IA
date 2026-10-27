MOTEUR DE CALCUL METIER - GUIDE DE TEST
=======================================

Acces : menu "Calculs" (barre laterale) ou http://localhost:3000/calculs

Onglets
  - Taux unique      : montant + dates + taux (%)  -> Resultat = Montant x (Taux/100) x (Jours/365)
  - Taux variables   : montant + periode globale -> periodes et taux lus dans le referentiel
  - Historique       : recherche, filtres, voir, modifier, supprimer, export PDF / Word
  - Periodes et taux : administration du referentiel (administrateurs uniquement)

Test rapide (exemples du cahier des charges)
  1. Taux unique : 25 000 / 18-02-2026 -> 29-06-2026 / 9,75 %      => 131 jours, 874,83
  2. Periodes et taux : ajouter les 6 periodes de l'exemple 2
     (ou executer backend/database/exemples/calculs_exemple_periodes.sql)
  3. Taux variables : 150 000 / 18-02-2026 -> 27-10-2026            => 252 jours, 10 408,56
  4. Historique : voir le calcul, exporter en PDF et en Word (rapport detaille / simplifie)

Conventions (modifiables, a valider avec l'encadrement)
  - Base annuelle : 365 jours. Montants arrondis au centime (arrondi commercial).
  - Case "Inclure le dernier jour" :
      decochee -> jours = fin - debut        (defaut du mode taux unique : 131 jours)
      cochee   -> jours = fin - debut + 1    (defaut du mode taux variables : 252 jours)
  - Taux variables : total = somme des resultats de chaque periode (deja arrondis).
  - Si une partie de la periode n'a pas de taux dans le referentiel, le calcul est refuse
    et les dates manquantes sont indiquees.
  - Suppression d'une periode du referentiel : supprimee si jamais utilisee, archivee si
    un calcul enregistre l'a utilisee (l'historique reste intact).

Tables creees automatiquement au premier acces (bases existantes comme nouvelles) :
  bareme_taux, periode_taux, calcul_taux (+ permissions du module "calculs").
Les roles autres que Admin n'ont acces qu'avec les permissions "calculs" (page Roles & Permissions).
