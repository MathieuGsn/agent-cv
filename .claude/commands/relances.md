---
description: Liste les relances à faire et propose un mail de relance pour chacune (jamais envoyé).
---

# /relances

1. Récupérer les relances du jour ou en retard :
   ```
   python scripts/candidatures.py relances --json
   ```
   (la règle des 30 jours → `Sans réponse` est appliquée au passage ; si des
   candidatures ont basculé, le mentionner).
2. S'il n'y en a aucune : le dire en une ligne, et donner la prochaine
   relance prévue si elle existe (`python scripts/candidatures.py list --json`,
   plus petite `date_relance_prevue` à venir).
3. Pour chaque relance, afficher :
   - entreprise, poste, date de candidature, jours de retard ;
   - destinataire si connu (`contact_nom` / `contact_email`), sinon indiquer
     "à envoyer via la plateforme ou au service recrutement" ;
   - **un mail de relance court et poli, prêt à copier-coller** : objet +
     corps de 4 à 6 phrases. Langue = celle de l'offre (lire
     `<chemin_dossier_offre>/offre.txt` ou `resultat.json` → `langue` si
     présent ; français par défaut). Contenu : rappel du poste et de la date
     de candidature, intérêt réel pour l'entreprise (s'appuyer uniquement sur
     ce que dit l'offre), disponibilité pour un stage de fin d'études de
     6 mois à partir de mars 2027, signature "Mathieu Gasnier". Pas de
     formules exagérées, aucune info inventée.
4. **Ne jamais envoyer de mail.** Aucun outil d'envoi ne doit être utilisé.
5. Terminer par : « Une fois envoyée, lance `/statut <entreprise> relancé` »
   (le passage en `Relancé` supprime la relance prévue : une seule relance).
