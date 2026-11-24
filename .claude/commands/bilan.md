---
description: Résumé rapide des candidatures (total, taux de réponse, entretiens, prochaines actions).
---

# /bilan

1. Récupérer les données :
   ```
   python scripts/candidatures.py bilan --json
   python scripts/candidatures.py a-faire
   ```
2. Répondre **court** (une dizaine de lignes max) :
   - Total, envoyées, à postuler ; en attente de réponse ; entretiens en
     cours ; offres ; refus ; sans réponse.
   - Taux de réponse (%) et délai moyen de réponse (jours), ou "pas encore
     assez de données" si vide.
   - **Prochaines actions**, par ordre d'urgence : relances en retard,
     entretiens à venir (date + entreprise), candidatures `À postuler` pas
     encore envoyées.
3. Si des candidatures sont marquées `(démo)`, préciser que ce sont des
   données de test.
4. Ne rien modifier dans la base.
