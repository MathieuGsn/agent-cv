---
description: Ajoute au suivi une candidature faite sans l'agent.
argument-hint: [entreprise] [poste] [infos libres : source, date, lien...]
---

# /ajout-candidature

Ajoute une candidature envoyée sans passer par `/adapter-cv` (CV de base,
candidature faite depuis le téléphone, etc.).

1. Récupérer depuis `$ARGUMENTS` ce qui est donné. Champs utiles :
   - **obligatoires** : entreprise, poste ;
   - **utiles** : statut (par défaut `Postulé` si Mathieu dit l'avoir déjà
     envoyée, sinon `À postuler`), date de candidature (aujourd'hui par
     défaut), source (Welcome to the Jungle, LinkedIn, Indeed, JobTeaser,
     HelloWork, APEC, Site entreprise, Candidature spontanée, Cooptation,
     Autre), lien de l'offre, ville, contact (nom, email), notes.
   - type de contrat : `Stage de fin d'études` par défaut.
2. S'il manque l'entreprise ou le poste, les demander. Pour le reste, **une
   seule question groupée** au maximum (source, date, statut) ; ne pas
   insister si Mathieu ne sait pas.
3. Vérifier qu'elle n'existe pas déjà :
   ```
   python scripts/candidatures.py find "<entreprise>"
   ```
   Si une candidature proche existe (même entreprise, poste similaire),
   demander s'il s'agit de la même avant d'en créer une autre.
4. Ajouter (dates au format `AAAA-MM-JJ`) :
   ```
   python scripts/candidatures.py add --entreprise "..." --poste "..." \
     --statut "Postulé" --date-candidature AAAA-MM-JJ --source "..." \
     [--lien-offre "..."] [--ville "..."] [--contact-nom "..."] \
     [--contact-email "..."] [--chemin-cv-pdf "output/cv_base.pdf"] [--notes "..."]
   ```
   Avec le statut `Postulé`, la relance est fixée à J+10 après la date de candidature.
5. Confirmer en une ligne (et la date de relance si `Postulé`).
