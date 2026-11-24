---
description: Marque une candidature comme envoyée (statut Postulé, relance à J+10).
argument-hint: <entreprise> [date JJ/MM/AAAA si ce n'est pas aujourd'hui]
---

# /postule

Passe la candidature à `$ARGUMENTS` en `Postulé`. Tout passe par
`scripts/candidatures.py` : ne jamais écrire dans `data/candidatures.db` à la main.

1. Chercher la candidature :
   ```
   python scripts/candidatures.py find "<entreprise>" --json
   ```
   - **Aucun résultat** : le dire, et proposer `/ajout-candidature` (sans
     rien créer soi-même).
   - **Plusieurs résultats** : demander à Mathieu laquelle (montrer pour
     chacune : entreprise, poste, statut, date d'ajout). Ne pas choisir à sa place.
   - **Un seul résultat** : continuer.
2. Si une date est donnée dans les arguments (ex : "hier", "20/11"), la
   convertir en `AAAA-MM-JJ`. Sinon c'est aujourd'hui.
3. Lancer :
   ```
   python scripts/candidatures.py postule <id> [--date AAAA-MM-JJ]
   ```
   La relance est fixée automatiquement à J+10 (une seule relance prévue).
4. Si la candidature était déjà `Postulé` ou plus loin dans le parcours
   (entretien, refus...), le signaler avant de lancer la commande et demander
   confirmation : on ne revient pas en arrière sans accord.
5. Répondre en une ou deux lignes : entreprise, poste, date de candidature,
   date de relance prévue (format JJ/MM/AAAA).
