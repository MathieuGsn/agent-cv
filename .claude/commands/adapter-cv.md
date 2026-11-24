---
description: Adapte le CV à une offre d'emploi donnée (texte, URL ou PDF) et génère le PDF final.
argument-hint: <texte collé | URL | chemin vers un PDF>
---

# /adapter-cv

Adapte le CV à l'offre fournie dans `$ARGUMENTS`, sans jamais modifier
`data/master_cv.yaml` (voir règles non négociables dans `CLAUDE.md`).
Une fois l'offre récupérée, produire le PDF **sans poser de question**, sauf
si une information manque vraiment pour continuer.

## 0. Récupérer l'offre

- Si `$ARGUMENTS` est un texte brut substantiel (pas juste une URL ou un
  chemin) : c'est le texte de l'offre, l'utiliser tel quel.
- Si `$ARGUMENTS` ressemble à une URL : la récupérer avec l'outil de
  récupération web disponible. Si l'accès échoue (contenu dynamique, paywall,
  blocage), demander à Mathieu de coller le texte à la place — ne pas deviner
  le contenu de l'offre.
- Si `$ARGUMENTS` est un chemin vers un PDF : extraire le texte (pdftotext via
  `scripts/_tools.find_tool`, ou lire le PDF directement).
- Déterminer l'entreprise et l'intitulé du poste à partir du texte récupéré.
- Créer le dossier `offres/<AAAA-MM-JJ>_<entreprise>_<poste>/` (date du jour,
  entreprise et poste slugifiés : minuscules, sans accents, espaces -> tirets).
- Sauvegarder le texte brut dans `offre.txt` de ce dossier.

## 1. Détecter la langue

Détecter la langue de l'offre (fr/en) : le CV généré sera dans cette langue
(`--lang fr` ou `--lang en` pour `scripts/build.py`, en s'appuyant sur les
champs bilingues déjà présents dans `master_cv.yaml`).

## 2. Analyser l'offre → `analyse.md`

Dans le dossier de l'offre, écrire `analyse.md` avec :
- Intitulé exact du poste
- Hard skills obligatoires vs souhaitées
- Outils et méthodes cités
- Soft skills recherchés
- Mots-clés qui reviennent plusieurs fois (ou qui sont mis en avant)

Écrire aussi `keywords.txt` dans le même dossier : un mot-clé/terme par ligne,
dérivé de l'analyse ci-dessus (hard skills + outils + mots-clés récurrents).
Ce fichier sert d'entrée à `scripts/keyword_score.py` — pas besoin d'être
exhaustif à l'excès, viser les ~15-30 termes les plus significatifs de l'offre.

## 3. Comparer aux compétences réelles (zéro invention)

Relire `data/master_cv.yaml` (tags des bullets, catégories de compétences) et
classer chaque mot-clé de l'offre en :
- **Présent** : Mathieu a réellement cette compétence/expérience (tags/texte
  du master qui correspondent, même avec un vocabulaire différent).
- **Absent** : aucune trace dans le master. **Ne jamais l'ajouter au CV.**
  Le lister pour le récap final ("compétences manquantes").

En cas de doute réel sur une compétence ambiguë, poser la question au lieu de
deviner — mais rester minimal, la plupart des cas doivent se résoudre sans
interruption.

## 4. Construire `cv_adapte.yaml`

Dans le dossier de l'offre, écrire `cv_adapte.yaml` (même schéma que
`data/master_cv.yaml`, mais c'est une **copie sélectionnée**, jamais le
master lui-même) :
- Titre/accroche proche de l'intitulé du poste, en gardant explicitement la
  mention du stage de fin d'études de 6 mois à partir de mars 2027.
- Sélection des expériences, projets et bullets les plus pertinents pour
  cette offre (utiliser les tags du master pour prioriser).
- Compétences réordonnées : celles demandées par l'offre en premier dans
  chaque catégorie.
- Reformulation avec le vocabulaire exact de l'offre **uniquement si ça
  décrit quelque chose de réellement fait** (ex : terme long + acronyme si
  pertinent, "Machine Learning (ML)").
- Phrases naturelles, pas de bourrage de mots-clés, pas de texte caché.
- Contenu calibré pour tenir sur une page (s'inspirer des plafonds par
  défaut de `scripts/build.py`, à ajuster si l'offre justifie d'inclure/
  exclure autre chose que les choix par défaut de `/build-cv`).

## 5. Compiler le PDF

```
python scripts/build.py --input offres/<dossier>/cv_adapte.yaml \
  --output "offres/<dossier>/Mathieu_Gasnier_CV_<Entreprise>.pdf" --lang <fr|en>
```

Comme `cv_adapte.yaml` est déjà pré-sélectionné, passer les plafonds
`--max-*` à `0` (désactivés) sauf si une coupe supplémentaire est nécessaire
pour tenir sur une page.

## 6. Vérifier et scorer

```
python scripts/ats_check.py "offres/<dossier>/Mathieu_Gasnier_CV_<Entreprise>.pdf" --lang <fr|en>
python scripts/keyword_score.py --keywords-file offres/<dossier>/keywords.txt \
  --before output/cv_base.pdf --after "offres/<dossier>/Mathieu_Gasnier_CV_<Entreprise>.pdf"
```

Si `ats_check.py` signale un problème, corriger `cv_adapte.yaml` ou le
template et recompiler avant de livrer.

## 7. Récap final (court)

Donner à Mathieu :
- Score de correspondance mots-clés avant → après (sortie de
  `keyword_score.py`).
- Liste des modifications faites (bullets/expériences mis en avant,
  compétences réordonnées, reformulations).
- Mots-clés de l'offre que Mathieu a peut-être mais qui manquent au master
  (à confirmer avec lui — ne pas les ajouter sans validation).
- Compétences demandées par l'offre qu'il n'a pas (listées, jamais ajoutées
  au CV).
- Chemin du PDF final.
