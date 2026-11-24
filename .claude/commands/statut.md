---
description: Change le statut d'une candidature (avec une note optionnelle).
argument-hint: <entreprise> <nouveau statut> [note]
---

# /statut

Arguments : `$ARGUMENTS` = `<entreprise> <nouveau statut> [note]`.

Statuts possibles (`python scripts/candidatures.py statuts`) :
`À postuler`, `Postulé`, `Relancé`, `Entretien RH`, `Test technique`,
`Entretien technique`, `Offre reçue`, `Acceptée`, et à tout moment `Refusé`,
`Sans réponse`, `Abandonné`.

1. Découper les arguments : le nom d'entreprise peut contenir des espaces, le
   statut peut être écrit sans accents ni majuscules ("entretien rh",
   "refuse", "test"). Ce qui suit le statut est la note.
   Si le statut ne correspond clairement à aucun de la liste, demander lequel.
2. Chercher la candidature :
   ```
   python scripts/candidatures.py find "<entreprise>" --json
   ```
   - Aucun résultat : le dire, proposer `/ajout-candidature`.
   - **Plusieurs résultats : demander à Mathieu laquelle** (entreprise, poste,
     statut actuel). Ne jamais deviner.
3. Lancer :
   ```
   python scripts/candidatures.py statut <id> "<Statut exact>" [--note "<note>"]
   ```
   Le changement est enregistré dans l'historique avec la date du jour.
   Règles appliquées par le script : `Postulé` → relance à J+10 ;
   `Relancé` ou statut de fin → plus de relance prévue.
4. Si la note donne une date d'entretien ("entretien le 3/12") ou un contact
   (nom, email du recruteur), proposer de l'enregistrer et, après accord :
   ```
   python scripts/candidatures.py set <id> --date-entretien AAAA-MM-JJ      [--contact-nom "..."] [--contact-email "..."]
   ```
5. Répondre en une ligne : ancien statut → nouveau statut.
