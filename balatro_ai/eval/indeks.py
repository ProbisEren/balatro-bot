"""`veri/` altındaki deney klasörlerinin içindekiler tablosu (`veri/INDEKS.md`).

Klasör adı biçimi: `NN_<ajan>_<küme>_<açıklama>`; NN deneyin sırasıdır. Tablo her çağrıda klasörlerden yeniden kurulur
(kayıtlar değişmez, tablo türetilmiştir).

    python -m balatro_ai.eval.indeks
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from balatro_ai.data.okuma import baglan

NUMARALI = re.compile(r"^(\d{2,})_")


def sonraki_deney_dizini(kok: str | Path, ajan: str, kume: str, ad: str) -> Path:
    """`<kok>/NN_<ajan>_<küme>_<ad>`: NN, mevcut en büyük numaranın bir fazlası."""
    kok = Path(kok)
    kok.mkdir(parents=True, exist_ok=True)
    numaralar = [int(m.group(1)) for d in kok.iterdir() if d.is_dir() and (m := NUMARALI.match(d.name))]
    temiz = lambda s: re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-") or "x"
    return kok / f"{max(numaralar, default=0) + 1:02d}_{temiz(ajan)}_{temiz(kume)}_{temiz(ad)}"


def tablo(kok: str | Path = "veri") -> str:
    kok = Path(kok)
    satirlar = [
        "# Deney klasörleri",
        "",
        "Klasör adı: `NN_ajan_küme_açıklama`, NN deneyin sırasıdır. Bu dosya `python -m balatro_ai.eval.indeks` ile yeniden üretilir.",
        "",
        "| Sıra | Klasör | Ajan | Küme | Run | Geçerli | Ort. son ante | Kazanan | İlk run |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for d in sorted(p for p in kok.iterdir() if p.is_dir() and list(p.glob("*.jsonl"))):
        con = baglan(d)
        r = con.execute(
            "SELECT count(*), sum(gecerli::int), round(avg(son_ante), 2), sum((durum = 'kazandi')::int), "
            "min(strftime(baslangic, '%Y-%m-%d %H:%M')), "
            "string_agg(DISTINCT json_extract_string(ajan, '$.tur'), ', '), string_agg(DISTINCT yaklasim, ', ') FROM runs"
        ).fetchone()
        m = NUMARALI.match(d.name)
        sira = m.group(1) if m else "-"
        satirlar.append(
            f"| {sira} | `{d.name}` | {r[5]} | {r[6]} | {r[0]} | {r[1]} | {r[2]} | {r[3] or 0} | {r[4]} |"
        )
    return "\n".join(satirlar) + "\n"


def yaz(kok: str | Path = "veri") -> Path:
    yol = Path(kok) / "INDEKS.md"
    yol.write_text(tablo(kok), encoding="utf-8")
    return yol


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kok", default="veri")
    args = ap.parse_args(argv)
    print(yaz(args.kok).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
