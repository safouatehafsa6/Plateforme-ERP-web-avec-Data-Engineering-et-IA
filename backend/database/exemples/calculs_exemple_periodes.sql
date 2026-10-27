-- OPTIONNEL : charge dans le barème « Taux de référence » les 6 périodes de l'exemple
-- du cahier des charges (taux variables 2026). À n'utiliser que pour une démonstration.
INSERT INTO periode_taux (bareme_id, date_debut, date_fin, taux, cree_par)
SELECT b.id, v.debut::date, v.fin::date, v.taux, 'exemple'
FROM bareme_taux b
CROSS JOIN (VALUES
  ('2026-02-18', '2026-03-09',  8.20),
  ('2026-03-10', '2026-04-24',  8.85),
  ('2026-04-25', '2026-06-18',  9.40),
  ('2026-06-19', '2026-08-08', 10.15),
  ('2026-08-09', '2026-09-21', 11.25),
  ('2026-09-22', '2026-10-27', 12.00)
) AS v(debut, fin, taux)
WHERE b.code = 'TAUX_REFERENCE'
  AND NOT EXISTS (SELECT 1 FROM periode_taux p WHERE p.bareme_id = b.id AND p.date_debut = v.debut::date);
