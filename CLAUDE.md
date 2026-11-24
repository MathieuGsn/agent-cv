# Agent CV — règles du projet

Ce dossier contient un générateur de CV LaTeX 100% ATS pour Mathieu Gasnier
(EFREI Paris, 5e année, majeure Data Engineering, diplôme 2027), qui cherche
un **stage de fin d'études de 6 mois à partir de mars 2027** en data.

## Règle n°1 (non négociable) : zéro invention

- Ne jamais ajouter une compétence, un outil, une expérience, un diplôme, un
  chiffre ou une certification qui n'existe pas réellement dans
  `data/master_cv.yaml` ou les sources (`sources/`).
- Reformuler, réordonner et utiliser le vocabulaire exact d'une offre est
  autorisé **uniquement si ça décrit quelque chose de réellement fait** (ex :
  "pipelines de données" → "pipelines ETL" si c'est vrai).
- Si une offre demande une compétence absente du master, elle est listée dans
  un rapport "compétences manquantes" (jamais ajoutée au CV). C'est à Mathieu
  de décider.
- En cas de doute, poser la question plutôt que deviner.

## Règle n°2 : confidentialité

- Le rapport de stage (`sources/rapport_stage.docx`) contient des captures
  d'écran et des annexes avec des **données sensibles réelles** : nom d'un
  client (nom volontairement omis ici, voir les notes locales), contacts nominatifs et emails de ce client, chiffres
  financiers internes (ARR/MRR, montants de devis). **Ces éléments ne doivent
  jamais apparaître dans un CV**, quelle que soit la version. Voir
  `data/notes_rapport_stage.md` pour le détail de ce qui a été exclu.
- Aucun nom de client, aucune donnée financière interne, aucune donnée
  personnelle d'un tiers ne doit figurer dans `data/master_cv.yaml` ni dans
  aucun CV généré.

## Source de vérité

`data/master_cv.yaml` est le **réservoir unique** de contenu (bilingue FR/EN).
Il peut contenir plus de bullets que ce qui tient sur une page — c'est voulu.
La phase 2 (adaptation à une offre) sélectionne un sous-ensemble dans un
fichier séparé (`offres/<dossier>/cv_adapte.yaml`) et **ne modifie jamais**
`data/master_cv.yaml`.

Pour mettre à jour une information (nouveau projet, certification, etc.),
modifier `data/master_cv.yaml` directement, jamais un CV généré.

## Contraintes du template LaTeX (`templates/cv_template.tex`)

- **Pas de photo**, une seule colonne, pas de `tabular`/`minipage` côte à côte
  pour la mise en page, pas de TikZ, pas d'images, pas d'icônes
  (fontawesome interdit), pas de barres de niveau.
- `\usepackage[T1]{fontenc}` + `\usepackage[utf8]{inputenc}` +
  `\input{glyphtounicode}` + `\pdfgentounicode=1` (obligatoire pour que le
  texte extrait par les ATS soit correct — vérifié que ça fonctionne avec
  MiKTeX sur ce poste).
- Titres de section standards : Formation / Expérience professionnelle /
  Projets / Compétences / Langues (FR), Education / Experience / Projects /
  Skills / Languages (EN).
- Coordonnées en texte brut en haut du document (pas de header/footer LaTeX).
- Format de dates uniforme : `MM/AAAA - MM/AAAA`.
- Police simple (Helvetica via `helvet`), 10-11pt, une page maximum.
- Métadonnées PDF via `hyperref` : `pdftitle`, `pdfauthor`, `pdfkeywords`.
- Toutes les chaînes utilisateur passent par le filtre Jinja `tex` (échappe
  `& % $ # _ { } ~ ^ \`) avant d'être injectées dans le `.tex`.

## Outils (installés via winget, chemins à connaître)

Les scripts Python localisent ces outils automatiquement (voir
`scripts/_tools.py` si présent, sinon logique de fallback dans chaque
script) : `shutil.which()` d'abord, puis chemins connus en secours, car le
PATH système n'est pas toujours rechargé dans une session de terminal déjà
ouverte après une installation winget.

- `pdflatex`, `pdftotext` (MiKTeX) : `%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\`
- `pandoc` : `%LOCALAPPDATA%\Pandoc\`
- Poppler (`pdftotext` alternatif) : sous
  `%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_*\poppler-*\Library\bin\`

## Workflow

- **Phase 1** (`/build-cv`) : génère le CV de base à partir de
  `data/master_cv.yaml` → `output/cv_base.pdf`, puis lance
  `scripts/ats_check.py` sur le résultat.
- **Phase 2** (`/adapter-cv <offre>`) : voir `.claude/commands/adapter-cv.md`.
  Crée `offres/<AAAA-MM-JJ>_<entreprise>_<poste>/` avec `offre.txt`,
  `analyse.md`, `cv_adapte.yaml`, `cv.tex`, le PDF final nommé
  `Mathieu_Gasnier_CV_<Entreprise>.pdf`, et un score de correspondance
  mots-clés avant/après (`scripts/keyword_score.py`).
- Une fois une offre donnée en phase 2, produire le PDF sans poser de
  questions, sauf si une information manque vraiment.
- Fin de `/adapter-cv` : écrire `resultat.json` puis
  `python scripts/candidatures.py enregistrer offres/<dossier>` (ajout ou
  mise à jour sans doublon dans le suivi, statut `À postuler`).

## Suivi des candidatures

- Base SQLite locale `data/candidatures.db` (données perso, ignorée par git).
  Toute lecture/écriture passe par `scripts/candidatures.py` (module + CLI) :
  ne jamais écrire dans la base à la main.
- Statuts : `À postuler` → `Postulé` → `Relancé` → `Entretien RH` →
  `Test technique` → `Entretien technique` → `Offre reçue` → `Acceptée`, et à
  tout moment `Refusé`, `Sans réponse`, `Abandonné`. Chaque changement va
  dans la table `historique`.
- Règles automatiques (dans `candidatures.py`) : `Postulé` → relance prévue à
  J+10 ; une seule relance (`Relancé` supprime la relance prévue) ;
  `Postulé`/`Relancé` depuis plus de 30 jours → `Sans réponse`.
- Le « score de correspondance » = score mots-clés de `keyword_score.py`
  (ne pas l'appeler « score ATS » : `ats_check.py` vérifie la lisibilité).
- Commandes : `/postule <entreprise>`, `/statut <entreprise> <statut> [note]`,
  `/ajout-candidature`, `/relances` (propose des mails, n'envoie **jamais**
  rien), `/bilan`. Si plusieurs candidatures correspondent : demander laquelle.

## Dashboard (`dashboard/`)

- Streamlit, lancé par `Lancer_Dashboard.bat` (ou
  `python -m streamlit run dashboard/app.py`), sur http://localhost:8501.
- L'onglet *Nouvelle candidature* lance `/adapter-cv` en headless
  (`dashboard/claude_runner.py`) : `claude -p` avec `--allowedTools` limité
  (lecture du projet, écriture dans `offres/` seulement, scripts du projet).
  Les traitements sont dans `offres/_jobs/<horodatage>/`. Protocole de fin de
  réponse : `DOSSIER_OFFRE:`, `QUESTION_DASHBOARD:`, `ERREUR_DASHBOARD:`.
- Style : `dashboard/style.css` + composants `dashboard/ui.py`. Thème clair
  uniquement (Streamlit 1.50 ne gère qu'un thème personnalisé).
- Captures d'écran publiques (README) : uniquement avec le profil fictif,
  `AGENT_CV_MASTER=data/master_cv.example.yaml`, jamais avec le vrai CV.
- Tests : `python -m unittest discover -s tests`.

## Points de validation avec Mathieu

Toujours montrer et attendre validation à ces étapes (ne pas les sauter) :
1. Résumé du rapport de stage avant de finaliser `master_cv.yaml`.
2. Contenu de `data/master_cv.yaml` avant de passer au template/build.
3. PDF final + texte extrait (`ats_check.py`) avant de considérer la phase 1
   terminée / avant de démarrer la phase 2.

## Git et dépôt public

- Le dépôt est **public** sur GitHub : aucune donnée perso ne doit y entrer.
  Le `.gitignore` exclut `data/master_cv.yaml`, `data/notes_rapport_stage.md`,
  `data/candidatures.db`, `offres/`, `sources/`, `output/`, `mails/`, les
  tokens et `.env`. Le profil fictif `data/master_cv.example.yaml` sert de
  démo. Avant chaque commit, vérifier la liste des fichiers ajoutés.
- Aucun email, téléphone ou nom de client codé en dur dans les scripts : les
  coordonnées sont lues dans le master CV.
- Messages de commit : courts, simples, en français, comme écrits par
  Mathieu. **Jamais** de ligne `Co-Authored-By: Claude` ni de mention
  "Generated with Claude Code" (désactivé aussi dans `.claude/settings.json`).
