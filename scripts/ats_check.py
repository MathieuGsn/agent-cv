"""Verifie qu'un CV PDF est lisible par un ATS.

Usage:
    python scripts/ats_check.py output/cv_base.pdf
    python scripts/ats_check.py offres/.../Mathieu_Gasnier_CV_Acme.pdf --max-pages 1

Verifie : nombre de pages, presence et ordre des sections attendues, lisibilite
de l'email et du telephone, absence de caracteres de remplacement (accents
casses), absence de mots visiblement fusionnes, et presence des metadonnees PDF.
"""
import argparse
import pathlib
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _tools import find_tool  # noqa: E402

SECTION_LABELS = {
    "fr": ["Formation", "Expérience professionnelle", "Projets", "Compétences", "Langues"],
    "en": ["Education", "Experience", "Projects", "Skills", "Languages"],
}

# Tokens longs legitimes (URLs, emails) a ne pas signaler comme "mots fusionnes".
_WHITELIST_PATTERNS = [
    re.compile(r"^[\w.+-]+@[\w.-]+$"),  # email
    re.compile(r"^[\w.-]+\.[a-z]{2,}(/[\w.-]+)*$", re.IGNORECASE),  # domaine / URL simplifiee
    re.compile(r"^\d[\d/()+.\- ]*$"),  # numeros de telephone / dates
]


def load_personal() -> dict:
    """Coordonnées lues dans le master CV (jamais codées en dur : le repo est public)."""
    import yaml

    data_dir = pathlib.Path(__file__).resolve().parent.parent / "data"
    for name in ("master_cv.yaml", "master_cv.example.yaml"):
        path = data_dir / name
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return (yaml.safe_load(f) or {}).get("personal", {}) or {}
    return {}


def extract_text(pdf_path: pathlib.Path) -> str:
    pdftotext = find_tool("pdftotext")
    result = subprocess.run(
        [pdftotext, "-enc", "UTF-8", str(pdf_path), "-"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Échec de pdftotext : {result.stderr.decode(errors='replace')}")
    return result.stdout.decode("utf-8", errors="replace")


def count_pages(text: str) -> int:
    # pdftotext separe chaque page par un form-feed (\x0c).
    return text.count("\x0c") or 1


def get_pdf_metadata(pdf_path: pathlib.Path) -> dict:
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfdocument import PDFDocument

    with open(pdf_path, "rb") as f:
        parser = PDFParser(f)
        doc = PDFDocument(parser)
        if not doc.info:
            return {}
        raw = doc.info[0]
        out = {}
        for k, v in raw.items():
            if isinstance(v, bytes):
                if v[:2] == b"\xfe\xff":
                    v = v.decode("utf-16-be", errors="replace")[1:]
                else:
                    try:
                        v = v.decode("utf-8")
                    except UnicodeDecodeError:
                        v = v.decode("latin-1", errors="replace")
            out[k] = v
        return out


def find_merged_words(text: str, min_len: int = 28) -> list:
    suspects = []
    for token in text.split():
        token = token.strip(".,;:()[]{}")
        if len(token) < min_len:
            continue
        if any(p.match(token) for p in _WHITELIST_PATTERNS):
            continue
        suspects.append(token)
    return suspects


def check_sections(text: str, labels: list) -> list:
    missing = []
    positions = []
    for label in labels:
        idx = text.find(label)
        if idx == -1:
            missing.append(label)
        else:
            positions.append((label, idx))
    out_of_order = []
    for (label_a, pos_a), (label_b, pos_b) in zip(positions, positions[1:]):
        if pos_a >= pos_b:
            out_of_order.append(f"{label_a} (pos {pos_a}) >= {label_b} (pos {pos_b})")
    return missing, out_of_order


def run_checks(pdf_path: pathlib.Path, lang: str, max_pages: int, email: str, phone: str) -> int:
    problems = []
    oks = []

    text = extract_text(pdf_path)

    pages = count_pages(text)
    if pages <= max_pages:
        oks.append(f"Pages : {pages} (<= {max_pages})")
    else:
        problems.append(f"Le PDF fait {pages} page(s), attendu <= {max_pages}.")

    if "�" in text:
        count = text.count("�")
        problems.append(f"{count} caractère(s) de remplacement U+FFFD trouvé(s) (accents cassés ?).")
    else:
        oks.append("Pas de caractère de remplacement U+FFFD (accents OK).")

    if email and email in text:
        oks.append(f"Email lisible : {email}")
    elif email:
        problems.append(f"Email '{email}' introuvable tel quel dans le texte extrait.")

    phone_digits = re.sub(r"\D", "", phone) if phone else ""
    text_digits = re.sub(r"\D", "", text)
    if phone_digits and phone_digits in text_digits:
        oks.append(f"Téléphone lisible : {phone}")
    elif phone:
        problems.append(f"Téléphone '{phone}' introuvable (en chiffres) dans le texte extrait.")

    labels = SECTION_LABELS.get(lang, SECTION_LABELS["fr"])
    missing, out_of_order = check_sections(text, labels)
    if missing:
        problems.append(f"Section(s) non détectée(s) : {', '.join(missing)}")
    else:
        oks.append(f"Toutes les sections attendues sont détectées ({', '.join(labels)}).")
    if out_of_order:
        problems.append("Ordre de lecture suspect : " + "; ".join(out_of_order))
    else:
        oks.append("Ordre de lecture des sections cohérent.")

    merged = find_merged_words(text)
    if merged:
        preview = ", ".join(merged[:8])
        problems.append(f"{len(merged)} mot(s) possiblement fusionné(s)/coupé(s) : {preview}")
    else:
        oks.append("Pas de mot visiblement fusionné ou coupé détecté.")

    meta = get_pdf_metadata(pdf_path)
    for key in ("Title", "Author"):
        if meta.get(key):
            oks.append(f"Métadonnée PDF '{key}' présente : {meta[key]!r}")
        else:
            problems.append(f"Métadonnée PDF '{key}' absente ou vide.")

    print(f"=== Vérification ATS : {pdf_path} ===\n")
    print("OK :")
    for o in oks:
        print(f"  [OK] {o}")
    if problems:
        print("\nProblèmes :")
        for p in problems:
            print(f"  [!!] {p}")
    print(f"\n--- Texte extrait ({len(text)} caractères) ---\n")
    print(text)

    print("\n=== Verdict :", "OK" if not problems else f"{len(problems)} PROBLEME(S)", "===")
    return 0 if not problems else 1


def main():
    parser = argparse.ArgumentParser(description="Vérifie la lisibilité ATS d'un CV PDF.")
    parser.add_argument("pdf", help="Chemin du PDF à vérifier")
    parser.add_argument("--lang", choices=["fr", "en"], default="fr")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--email", default=None, help="Par défaut : personal.email du master CV")
    parser.add_argument("--phone", default=None, help="Par défaut : personal.phone du master CV")
    args = parser.parse_args()

    personal = load_personal()
    if args.email is None:
        args.email = personal.get("email") or ""
    if args.phone is None:
        args.phone = personal.get("phone") or ""

    pdf_path = pathlib.Path(args.pdf)
    if not pdf_path.is_absolute():
        root = pathlib.Path(__file__).resolve().parent.parent
        pdf_path = root / pdf_path

    exit_code = run_checks(pdf_path, args.lang, args.max_pages, args.email, args.phone)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
