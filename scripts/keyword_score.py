"""Score de correspondance mots-clés entre une offre et un CV (avant/après adaptation).

La liste de mots-clés est fournie par l'appelant (typiquement extraite d'une offre
pendant l'analyse en phase 2) -- ce script ne fait pas de NLP, seulement la
normalisation et le calcul du score.

Usage:
    python scripts/keyword_score.py --keywords-file offres/.../keywords.txt --cv output/cv_base.pdf
    python scripts/keyword_score.py --keywords "Power BI,ETL,Python,Machine Learning" \
        --before output/cv_base.pdf --after offres/.../Mathieu_Gasnier_CV_Acme.pdf
"""
import argparse
import pathlib
import re
import subprocess
import sys
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _tools import find_tool  # noqa: E402


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def singularize(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def normalize_spaced(text: str) -> str:
    text = strip_accents(text.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = [singularize(w) for w in text.split()]
    return " ".join(words)


def normalize_squashed(text: str) -> str:
    return normalize_spaced(text).replace(" ", "")


def load_keywords(args) -> list:
    keywords = []
    if args.keywords_file:
        path = pathlib.Path(args.keywords_file)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("-*• ").strip()
            if line:
                keywords.append(line)
    if args.keywords:
        keywords.extend(k.strip() for k in args.keywords.split(",") if k.strip())
    # dédoublonnage en conservant l'ordre
    seen = set()
    out = []
    for k in keywords:
        key = normalize_squashed(k)
        if key and key not in seen:
            seen.add(key)
            out.append(k)
    return out


def extract_text(cv_path: pathlib.Path) -> str:
    if cv_path.suffix.lower() == ".pdf":
        pdftotext = find_tool("pdftotext")
        result = subprocess.run(
            [pdftotext, "-enc", "UTF-8", str(cv_path), "-"], capture_output=True
        )
        if result.returncode != 0:
            raise SystemExit(f"Échec de pdftotext : {result.stderr.decode(errors='replace')}")
        return result.stdout.decode("utf-8", errors="replace")
    return cv_path.read_text(encoding="utf-8", errors="replace")


def score_cv(keywords: list, cv_text: str) -> dict:
    spaced_text = normalize_spaced(cv_text)
    squashed_text = normalize_squashed(cv_text)
    padded_spaced = f" {spaced_text} "

    matched, missing = [], []
    for kw in keywords:
        norm_spaced_kw = normalize_spaced(kw)
        norm_squashed_kw = normalize_squashed(kw)
        hit = f" {norm_spaced_kw} " in padded_spaced or (
            norm_squashed_kw and norm_squashed_kw in squashed_text
        )
        (matched if hit else missing).append(kw)

    total = len(keywords)
    pct = round(100 * len(matched) / total, 1) if total else 0.0
    return {"matched": matched, "missing": missing, "total": total, "percent": pct}


def print_report(label: str, result: dict):
    print(f"--- {label} : {result['percent']}% ({len(result['matched'])}/{result['total']}) ---")
    if result["matched"]:
        print("  Présents :", ", ".join(result["matched"]))
    if result["missing"]:
        print("  Absents  :", ", ".join(result["missing"]))
    print()


def resolve_path(p: str) -> pathlib.Path:
    path = pathlib.Path(p)
    if not path.is_absolute():
        root = pathlib.Path(__file__).resolve().parent.parent
        path = root / path
    return path


def main():
    parser = argparse.ArgumentParser(description="Score de correspondance mots-clés offre <-> CV.")
    parser.add_argument("--keywords-file", help="Fichier texte, un mot-clé par ligne")
    parser.add_argument("--keywords", help="Liste de mots-clés séparés par des virgules")
    parser.add_argument("--cv", help="CV unique à scorer (PDF ou texte)")
    parser.add_argument("--before", help="CV de référence (ex: cv_base.pdf) pour comparaison avant/après")
    parser.add_argument("--after", help="CV adapté pour comparaison avant/après")
    args = parser.parse_args()

    keywords = load_keywords(args)
    if not keywords:
        raise SystemExit("Aucun mot-clé fourni (--keywords-file ou --keywords requis).")

    if args.cv:
        cv_path = resolve_path(args.cv)
        text = extract_text(cv_path)
        result = score_cv(keywords, text)
        print_report(str(cv_path.name), result)
        return

    if args.before and args.after:
        before_path, after_path = resolve_path(args.before), resolve_path(args.after)
        before_result = score_cv(keywords, extract_text(before_path))
        after_result = score_cv(keywords, extract_text(after_path))
        print_report(f"Avant ({before_path.name})", before_result)
        print_report(f"Après ({after_path.name})", after_result)
        newly_matched = sorted(set(after_result["matched"]) - set(before_result["matched"]))
        still_missing = after_result["missing"]
        print(f"Évolution du score : {before_result['percent']}% -> {after_result['percent']}%")
        if newly_matched:
            print("Nouveaux mots-clés couverts :", ", ".join(newly_matched))
        if still_missing:
            print("Toujours absents (compétences manquantes à confirmer) :", ", ".join(still_missing))
        return

    raise SystemExit("Fournir --cv seul, ou --before et --after pour une comparaison.")


if __name__ == "__main__":
    main()
