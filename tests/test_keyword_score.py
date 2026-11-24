"""Tests du score de correspondance (scripts/keyword_score.py).

Lancer : python -m unittest discover -s tests
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from keyword_score import score_cv  # noqa: E402


def trouve(mot_cle: str, texte: str) -> bool:
    return mot_cle in score_cv([mot_cle], texte)["matched"]


class MotsClesCourts(unittest.TestCase):
    """ETL, SQL, AWS, C, R, Java... : comptés seulement comme mot entier."""

    def test_etl_pas_dans_un_autre_mot(self):
        self.assertFalse(trouve("ETL", "Settlement et complétlement autre chose"))

    def test_etl_mot_entier(self):
        self.assertTrue(trouve("ETL", "Conception de pipelines ETL en Python"))
        self.assertTrue(trouve("ETL", "Flux ETL/ELT quotidiens"))

    def test_sql_pas_dans_postgresql(self):
        self.assertFalse(trouve("SQL", "Base PostgreSQL et MySQL"))
        self.assertTrue(trouve("SQL", "Python, SQL, Java"))

    def test_aws(self):
        self.assertFalse(trouve("AWS", "Les laws et drawsheets"))
        self.assertTrue(trouve("AWS", "AWS (Lambda, API Gateway)"))

    def test_c_et_r_une_lettre(self):
        self.assertFalse(trouve("C", "HTML/CSS et Recherche sémantique"))
        self.assertFalse(trouve("R", "HTML/CSS et Recherche sémantique"))
        self.assertTrue(trouve("C", "Langages : Python, Java, C, SQL"))
        self.assertTrue(trouve("R", "Statistiques avec R et Python"))

    def test_java_pas_dans_javascript(self):
        self.assertFalse(trouve("Java", "HTML/CSS/JavaScript"))
        self.assertTrue(trouve("Java", "Python, Java, C"))


class MotsClesLongs(unittest.TestCase):
    """Les mots-clés longs gardent la tolérance sur l'espacement et la ponctuation."""

    def test_power_bi_colle(self):
        self.assertTrue(trouve("Power BI", "Tableaux de bord PowerBI"))

    def test_scikit_learn(self):
        self.assertTrue(trouve("scikit-learn", "pandas, scikit learn, NLP"))

    def test_pluriel_et_accents(self):
        self.assertTrue(trouve("pipeline de données", "Pipelines de donnees (ingestion, API)"))

    def test_absent(self):
        self.assertFalse(trouve("Airflow", "Python, SQL, AWS"))


if __name__ == "__main__":
    unittest.main()
