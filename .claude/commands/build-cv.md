---
description: Génère le CV de base (FR) depuis data/master_cv.yaml et vérifie sa conformité ATS.
---

# /build-cv

Génère `output/cv_base.pdf` depuis `data/master_cv.yaml` (la source de vérité —
voir `CLAUDE.md`), puis vérifie sa lisibilité ATS.

## Étapes

1. Lancer la génération :
   ```
   python scripts/build.py --input data/master_cv.yaml --output output/cv_base.pdf --lang fr
   ```
   Les plafonds par défaut (`--max-bullets-exp 6`, `--max-projects 3`,
   `--max-experiences 1`, etc., voir `scripts/build.py --help`) sont calibrés
   pour tenir sur une page avec le contenu actuel de `master_cv.yaml`. Si le
   master a changé (nouvelle expérience, bullets ajoutés...), ces valeurs
   peuvent nécessiter un ajustement — voir étape 3.

2. Lancer la vérification ATS :
   ```
   python scripts/ats_check.py output/cv_base.pdf --lang fr
   ```

3. Si `ats_check.py` signale plus d'une page ou un problème :
   - D'abord resserrer le contenu via les flags de `build.py` (moins de
     bullets/projets/compétences) plutôt que de dégrader l'espacement du
     template en dessous de ce qui est déjà réglé dans
     `templates/cv_template.tex` (marges ~1.5-1.6cm, déjà assez serrées).
   - Ne jamais couper un mot ou une phrase au milieu pour gagner de la place.
   - Ne jamais inventer de contenu pour combler de l'espace vide.

4. Montrer à Mathieu :
   - Le PDF généré (`output/cv_base.pdf`).
   - Le rapport `ats_check.py` (OK / problèmes).
   - Ce qui a été inclus vs laissé de côté par les plafonds par défaut (ex:
     emplois étudiants, catégorie Systèmes d'exploitation) pour qu'il valide
     ces choix.

5. Attendre sa validation avant de considérer la phase 1 terminée ou de passer
   à `/adapter-cv`.

## Génération en anglais

Pour une version anglaise de base : même commande avec `--lang en`
(les champs bilingues de `master_cv.yaml` sont déjà prêts pour ça).
