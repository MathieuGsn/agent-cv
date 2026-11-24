# Agent CV — Mathieu Gasnier

Générateur de CV LaTeX 100% ATS (sans photo, une colonne, texte extractible
proprement), avec adaptation automatique à une offre d'emploi.

Voir `CLAUDE.md` pour les règles non négociables (zéro invention,
confidentialité, contraintes du template).

## Structure

```
data/master_cv.yaml        # source de vérité (réservoir complet, bilingue FR/EN)
templates/cv_template.tex  # template LaTeX ATS (Jinja2)
scripts/build.py           # yaml -> tex -> pdf
scripts/ats_check.py       # vérifie la lisibilité ATS d'un PDF
scripts/keyword_score.py   # score de correspondance mots-clés offre <-> CV
output/cv_base.pdf          # CV de base (phase 1)
offres/<date>_<entreprise>_<poste>/   # un dossier par candidature (phase 2)
```

## Utilisation

- `/build-cv` : (re)génère le CV de base à partir de `data/master_cv.yaml`.
- `/adapter-cv <offre>` : adapte le CV à une offre (texte collé, URL ou PDF) et
  génère `offres/<dossier>/Mathieu_Gasnier_CV_<Entreprise>.pdf`.

## Mettre à jour le CV

Modifier uniquement `data/master_cv.yaml` (jamais un CV généré directement),
puis relancer `/build-cv`.

## Outils requis

`pdflatex` (MiKTeX), `pandoc`, `pdftotext` (Poppler), Python avec
`pyyaml`, `jinja2`, `python-docx`, `pdfminer.six`. Les scripts localisent ces
binaires automatiquement (`scripts/_tools.py`) même si le PATH du terminal
n'a pas été rechargé après une installation.
