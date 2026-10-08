"""Kod açıklama kuralının denetimi: her dosya, sınıf ve fonksiyonun başında ne işe yaradığı yazmalı."""

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _eksikler() -> list[str]:
    """`balatro_ai/` ve `tests/` altındaki açıklaması (docstring veya hemen üstünde yorum) olmayan kod parçalarını listeler."""
    eksik: list[str] = []
    for dosya in sorted([*KOK.glob("balatro_ai/**/*.py"), *KOK.glob("tests/*.py")]):
        kaynak = dosya.read_text(encoding="utf-8")
        if not kaynak.strip():
            continue  # boş __init__.py dosyaları
        satirlar = kaynak.splitlines()
        agac = ast.parse(kaynak)
        goreli = dosya.relative_to(KOK)
        if not ast.get_docstring(agac):
            eksik.append(f"{goreli}: modül açıklaması yok")

        def gez(dugum: ast.AST, ad: str = "") -> None:
            """Düğümün alt sınıf ve fonksiyonlarını özyinelemeli gezer, açıklaması eksik olanı listeye ekler."""
            for c in ast.iter_child_nodes(dugum):
                if isinstance(c, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                    q = f"{ad}.{c.name}" if ad else c.name
                    ust = c.lineno - 2
                    while ust >= 0 and satirlar[ust].strip().startswith("@"):
                        ust -= 1
                    yorum_var = ust >= 0 and satirlar[ust].strip().startswith("#")
                    if not ast.get_docstring(c) and not yorum_var:
                        eksik.append(f"{goreli}:{c.lineno}: {q} için açıklama yok")
                    gez(c, q)

        gez(agac)
    return eksik


def test_her_kod_parcasinin_basinda_aciklama_var():
    """Açıklaması olmayan modül, sınıf veya fonksiyon bulunmadığını doğrular (kullanıcı kuralı)."""
    eksik = _eksikler()
    assert not eksik, "Açıklaması eksik kod:\n" + "\n".join(eksik[:25])
