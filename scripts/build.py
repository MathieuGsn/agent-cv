"""Genere un CV PDF ATS a partir d'un fichier YAML (master ou adapte a une offre).

Usage:
    python scripts/build.py --input data/master_cv.yaml --output output/cv_base.pdf --lang fr
    python scripts/build.py --input offres/2026-11-11_acme_data-engineer/cv_adapte.yaml \
        --output offres/2026-11-11_acme_data-engineer/Mathieu_Gasnier_CV_Acme.pdf --lang fr
"""
import argparse
import pathlib
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import jinja2
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _tools import find_tool  # noqa: E402

LABELS = {
    "fr": {
        "education": "Formation",
        "experience": "Expérience professionnelle",
        "complementary_experiences": "Expériences complémentaires",
        "projects": "Projets",
        "skills": "Compétences",
        "languages": "Langues",
        "interests": "Centres d'intérêt",
        "certifications": "Certifications",
    },
    "en": {
        "education": "Education",
        "experience": "Experience",
        "complementary_experiences": "Additional Experience",
        "projects": "Projects",
        "skills": "Skills",
        "languages": "Languages",
        "interests": "Interests",
        "certifications": "Certifications",
    },
}

_TEX_REPLACEMENTS = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]


def tex_escape(value) -> str:
    if value is None:
        return ""
    s = str(value)
    for old, new in _TEX_REPLACEMENTS:
        s = s.replace(old, new)
    return s


def localize(value, lang):
    if isinstance(value, dict) and "fr" in value and "en" in value:
        return value.get(lang, value.get("fr"))
    if isinstance(value, list):
        return [localize(v, lang) for v in value]
    return value


def build_context(
    data,
    lang,
    max_bullets_exp=None,
    max_bullets_project=None,
    max_projects=None,
    max_experiences=None,
    max_skill_items=None,
    max_soft_skills=None,
    exclude_skill_categories=None,
):
    personal = dict(data["personal"])
    if personal.get("github_url"):
        personal["github_display"] = personal["github_url"]

    education = []
    for edu in data["education"]:
        education.append(
            {
                "institution": edu["institution"],
                "degree": localize(edu["degree"], lang),
                "dates": localize(edu["dates"], lang),
                "details": localize(edu.get("details", {}), lang) or [],
            }
        )

    raw_experiences = data["experiences"]
    if max_experiences:
        raw_experiences = raw_experiences[:max_experiences]
    experiences = []
    for exp in raw_experiences:
        bullets = exp["bullets"]
        if max_bullets_exp:
            bullets = bullets[:max_bullets_exp]
        experiences.append(
            {
                "title": localize(exp["title"], lang),
                "company": exp["company"],
                "location": exp["location"],
                "dates": localize(exp["dates"], lang),
                "context": localize(exp.get("context"), lang) or "",
                "bullets": localize(bullets, lang),
            }
        )

    complementary_experiences = []
    for exp in data.get("complementary_experiences", []):
        complementary_experiences.append(
            {
                "title": localize(exp["title"], lang),
                "company": exp["company"],
                "location": exp["location"],
                "dates": localize(exp["dates"], lang),
            }
        )

    raw_projects = data.get("projects", [])
    if max_projects:
        raw_projects = raw_projects[:max_projects]
    projects = []
    for proj in raw_projects:
        bullets = proj["bullets"]
        if max_bullets_project:
            bullets = bullets[:max_bullets_project]
        projects.append(
            {
                "title": localize(proj["title"], lang),
                "dates": localize(proj.get("dates"), lang),
                "bullets": localize(bullets, lang),
            }
        )

    exclude_categories = set(exclude_skill_categories or [])
    skills = []
    visible_keywords = []
    for cat in data.get("skills", []):
        cat_label_fr = cat["category"].get("fr") if isinstance(cat["category"], dict) else cat["category"]
        if cat_label_fr in exclude_categories:
            continue
        items = cat["items"][:max_skill_items] if max_skill_items else cat["items"]
        skills.append({"category": localize(cat["category"], lang), "text": ", ".join(items)})
        visible_keywords.extend(items)

    # max_soft_skills=0 (defaut) masque entierement la ligne Savoir-etre.
    soft_skills = localize(data.get("soft_skills", []), lang)
    if max_soft_skills is not None:
        soft_skills = soft_skills[:max_soft_skills]
    if soft_skills:
        skills.append(
            {
                "category": "Savoir-être" if lang == "fr" else "Soft skills",
                "text": ", ".join(soft_skills),
            }
        )
        visible_keywords.extend(soft_skills)

    languages = []
    for lg in data.get("languages", []):
        languages.append({"name": localize(lg["name"], lang), "level": localize(lg["level"], lang)})

    interests = data.get("interests") or []
    interests_str = ", ".join(localize(interests, lang)) if interests else ""

    certifications = localize(data.get("certifications", []), lang) or []

    # Les mots-cles des metadonnees PDF doivent correspondre exactement aux
    # competences visibles sur le CV (pas au reservoir complet du master).
    keywords = ", ".join(visible_keywords)

    meta = {
        "pdftitle": f"CV - {personal['name']}",
        "pdfauthor": personal["name"],
        "pdfkeywords": keywords,
    }

    return {
        "personal": personal,
        "headline": localize(data["headline"], lang),
        "education": education,
        "experiences": experiences,
        "complementary_experiences": complementary_experiences,
        "projects": projects,
        "skills": skills,
        "languages": languages,
        "interests": interests_str,
        "certifications": certifications,
        "labels": LABELS[lang],
        "meta": meta,
    }


def render_tex(context, template_path: pathlib.Path) -> str:
    env = jinja2.Environment(
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
    )
    env.filters["tex"] = tex_escape
    template = env.get_template(template_path.name)
    return template.render(**context)


def compile_pdf(tex_path: pathlib.Path) -> None:
    pdflatex = find_tool("pdflatex")
    out_dir = tex_path.parent
    for _ in range(2):
        result = subprocess.run(
            [
                pdflatex,
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-output-directory={out_dir}",
                tex_path.name,
            ],
            cwd=out_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log_path = tex_path.with_suffix(".log")
            tail = ""
            if log_path.exists():
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            print(result.stdout[-3000:])
            print(tail)
            raise SystemExit(f"Échec de compilation LaTeX ({tex_path.name}).")
    for ext in (".aux", ".log", ".out"):
        p = tex_path.with_suffix(ext)
        if p.exists():
            p.unlink()


def main():
    parser = argparse.ArgumentParser(description="Génère un CV PDF ATS depuis un YAML.")
    parser.add_argument("--input", default="data/master_cv.yaml")
    parser.add_argument("--output", default="output/cv_base.pdf")
    parser.add_argument("--lang", choices=["fr", "en"], default="fr")
    parser.add_argument("--template", default="templates/cv_template.tex")
    # Les valeurs par defaut ci-dessous visent a produire un CV de base tenant
    # sur une page a partir du reservoir complet. La phase 2 (offres/.../cv_adapte.yaml)
    # fournit deja un contenu pre-selectionne : passer --max-xxx 0 ou une valeur
    # plus large pour desactiver un plafond si l'offre le justifie.
    parser.add_argument("--max-bullets-exp", type=int, default=6)
    parser.add_argument("--max-bullets-project", type=int, default=3)
    parser.add_argument("--max-projects", type=int, default=3)
    parser.add_argument("--max-experiences", type=int, default=1)
    parser.add_argument("--max-skill-items", type=int, default=0)
    parser.add_argument("--max-soft-skills", type=int, default=0)
    parser.add_argument(
        "--exclude-skill-category",
        action="append",
        default=None,
        help="Repetable. Aucune categorie exclue par defaut.",
    )
    args = parser.parse_args()
    if args.exclude_skill_category is None:
        args.exclude_skill_category = []

    root = pathlib.Path(__file__).resolve().parent.parent

    def resolve(p):
        p = pathlib.Path(p)
        return p if p.is_absolute() else root / p

    input_path = resolve(args.input)
    if not input_path.exists() and args.input == "data/master_cv.yaml":
        # Clone public du repo : pas de master perso, on utilise le profil fictif.
        input_path = resolve("data/master_cv.example.yaml")
        print(f"data/master_cv.yaml absent -> utilisation de {input_path.name}")
    output_path = resolve(args.output)
    template_path = resolve(args.template)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    context = build_context(
        data,
        args.lang,
        max_bullets_exp=args.max_bullets_exp,
        max_bullets_project=args.max_bullets_project,
        max_projects=args.max_projects,
        max_experiences=args.max_experiences,
        max_skill_items=args.max_skill_items,
        max_soft_skills=args.max_soft_skills,
        exclude_skill_categories=args.exclude_skill_category,
    )
    tex_content = render_tex(context, template_path)

    tex_path = output_path.with_suffix(".tex")
    tex_path.write_text(tex_content, encoding="utf-8")

    compile_pdf(tex_path)

    produced_pdf = tex_path.with_suffix(".pdf")
    if produced_pdf != output_path:
        produced_pdf.replace(output_path)

    print(f"PDF généré : {output_path}")


if __name__ == "__main__":
    main()
