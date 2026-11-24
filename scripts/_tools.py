"""Localisation robuste des binaires externes (pdflatex, pdftotext, pandoc).

Sur Windows, le PATH système n'est pas toujours rechargé dans une session de
terminal déjà ouverte après une installation winget. On essaie d'abord
`shutil.which`, puis une liste de chemins connus en secours.
"""
import glob
import os
import shutil

_FALLBACK_GLOBS = {
    "pdflatex": [
        r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe",
        r"%PROGRAMFILES%\MiKTeX\miktex\bin\x64\pdflatex.exe",
    ],
    "pdftotext": [
        r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdftotext.exe",
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_*\poppler-*\Library\bin\pdftotext.exe",
    ],
    "pdftoppm": [
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_*\poppler-*\Library\bin\pdftoppm.exe",
        r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdftoppm.exe",
    ],
    "pandoc": [
        r"%LOCALAPPDATA%\Pandoc\pandoc.exe",
    ],
}


def find_tool(name: str) -> str:
    """Return a usable path/command for `name`, or raise FileNotFoundError."""
    found = shutil.which(name)
    if found:
        return found

    for pattern in _FALLBACK_GLOBS.get(name, []):
        expanded = os.path.expandvars(pattern)
        matches = sorted(glob.glob(expanded))
        if matches:
            return matches[-1]

    raise FileNotFoundError(
        f"Impossible de trouver '{name}'. Vérifie l'installation "
        f"(voir CLAUDE.md, section Outils) ou ouvre un nouveau terminal "
        f"pour que le PATH soit à jour."
    )
