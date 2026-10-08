"""Kayıtlı gerçek run'lardan oynanan elleri (kartlar, oyunun verdiği el türü ve skor farkı) çıkarır.

Puan motorunu gerçek oyuna karşı doğrulamak için kullanılır. Her örnek tek bir `play` komutudur.

    python -m balatro_ai.eval.el_ornekleri veri/soak-dar veri/soak-tam -o tests/veri/gercek_eller.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def run_dosyasindan(dosya: Path) -> list[dict[str, Any]]:
    ornekler = []
    for satir in dosya.read_text(encoding="utf-8").splitlines():
        k = json.loads(satir)
        if k.get("tip") != "karar" or k.get("hata") or not k.get("komut"):
            continue
        if k["komut"]["yontem"] != "play" or not k.get("cevap"):
            continue
        once, sonra = k["ham_durum"], k["cevap"]
        el = once["hand"]["cards"]
        secilen = k["komut"]["parametreler"]["cards"]
        turler = [
            t for t, v in once["hands"].items()
            if sonra["hands"][t]["played"] > v["played"]
        ]
        simdiki = next((b for b in once["blinds"].values() if b["status"] == "CURRENT"), {})
        ornekler.append(
            {
                "run": dosya.stem,
                "adim": k["adim"],
                "oynanan": [el[i]["key"] for i in secilen],
                "oynanan_modifier": [el[i].get("modifier") for i in secilen],
                "oynanan_durum": [el[i].get("state") for i in secilen],
                "elde_durum": [c.get("state") for i, c in enumerate(el) if i not in secilen],
                "jokerler": [j["key"] for j in once["jokers"]["cards"]],
                "elde": [c["key"] for i, c in enumerate(el) if i not in secilen],
                "el_degerleri": {t: [v["chips"], v["mult"]] for t, v in once["hands"].items()},
                "beklenen_tur": turler[0] if len(turler) == 1 else None,
                "skor_once": once["round"]["chips"],
                "skor_sonra": sonra["round"]["chips"],
                "blind": simdiki.get("type"),
                "blind_adi": simdiki.get("name"),
                "sonraki_faz": sonra["state"],
            }
        )
    return ornekler


def topla(dizinler: list[str]) -> list[dict[str, Any]]:
    tum: list[dict[str, Any]] = []
    for d in dizinler:
        for f in sorted(Path(d).glob("*.jsonl")):
            tum += run_dosyasindan(f)
    return tum


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dizinler", nargs="+")
    ap.add_argument("-o", "--cikti", required=True)
    args = ap.parse_args(argv)
    ornekler = topla(args.dizinler)
    Path(args.cikti).write_text(json.dumps(ornekler, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(ornekler)} el yazıldı: {args.cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
