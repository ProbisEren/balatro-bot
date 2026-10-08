"""Kaydedilmiş bir run'ı aynı seed ve aynı aksiyonlarla gerçek oyunda yeniden oynatır.

Amaç determinizmi ölçmek: aynı seed + aynı komutlar, her adımda aynı oyun durumunu vermeli mi?
Oyunun kart `id` alanları oturum boyunca artan sayaçtır, bu yüzden karşılaştırmada atılır.

    python -m balatro_ai.eval.tekrar veri/soak-dar/<run_id>.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from balatro_ai.env.client import BalatroIstemci
from balatro_ai.env.ortam import BalatroOrtami

ATILAN_ALANLAR = frozenset({"id"})


def normallestir(o: Any) -> Any:
    """Durumdan oturuma özgü `id` alanlarını atar (karşılaştırmanın anlamlı olması için)."""
    if isinstance(o, dict):
        return {k: normallestir(v) for k, v in o.items() if k not in ATILAN_ALANLAR}
    if isinstance(o, list):
        return [normallestir(v) for v in o]
    return o


def ilk_fark(a: Any, b: Any, yol: str = "") -> tuple[str, Any, Any] | None:
    """İki iç içe yapı arasındaki ilk farkın yolunu ve iki değerini döndürür; aynıysa None."""
    if type(a) is not type(b):
        return (yol or "/", a, b)
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return (f"{yol}/{k}", a.get(k, "<yok>"), b.get(k, "<yok>"))
            f = ilk_fark(a[k], b[k], f"{yol}/{k}")
            if f:
                return f
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return (f"{yol}[len]", len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            f = ilk_fark(x, y, f"{yol}[{i}]")
            if f:
                return f
        return None
    return None if a == b else (yol or "/", a, b)


def oku(dosya: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Bir run kaydını okur: ilk satır (run_basi) ve karar kayıtları."""
    satirlar = [json.loads(s) for s in Path(dosya).read_text(encoding="utf-8").splitlines()]
    return satirlar[0], [s for s in satirlar if s["tip"] == "karar"]


def tekrar_oynat(istemci: Any, dosya: str | Path, **ortam_ayarlari: Any) -> dict[str, Any]:
    """Kayıtlı run'ı aynı seed ve aynı aksiyonlarla oynatıp her adımda durumun kayıttakiyle aynı olduğunu denetler.
    """
    basi, kararlar = oku(dosya)
    kume = next((k["ek"].get("kume") for k in kararlar if k["ek"].get("kume")), "dar")
    env = BalatroOrtami(istemci, kume=kume, **ortam_ayarlari)
    # Seçilen aksiyonlar (oyunun kabul ettikleri); reddedilenler durumu değiştirmedi.
    adimlar = [k for k in kararlar if not k["ek"].get("otomatik") and k["hata"] is None and k["komut"]]
    env.reset(options={"oyun_seed": basi["seed"], "deste": basi["deste"], "stake": basi["stake"]})
    env._hedef_gereksinimi = {
        k: tuple(v) for k, v in (kararlar[-1]["ek"].get("hedef_gereksinimi") or {}).items()
    }
    # Başlangıç durumu: ilk botun karar anındaki ham durum.
    sonuc: dict[str, Any] = {"adim": len(adimlar), "tutarli_adim": 0, "ilk_fark": None, "durum": "tamam"}
    for i, k in enumerate(adimlar):
        beklenen = normallestir(k["ham_durum"])
        fark = ilk_fark(beklenen, normallestir(env._durum))
        if fark:
            sonuc["ilk_fark"] = {"adim": k["adim"], "yol": fark[0], "kayitli": fark[1], "simdi": fark[2]}
            sonuc["durum"] = "farkli"
            break
        sonuc["tutarli_adim"] = i + 1
        _, _, bitti, kesildi, _ = env.step(k["ek"]["aksiyon_id"])
        if (bitti or kesildi) and i < len(adimlar) - 1:
            sonuc["durum"] = "erken_bitti"
            break
    env.close()
    return sonuc


def main(argv: list[str] | None = None) -> int:
    """Komut satırı girişi: bir run kaydını yeniden oynatıp sonucu yazdırır."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dosya")
    args = ap.parse_args(argv)
    sonuc = tekrar_oynat(BalatroIstemci(zaman_asimi=60), args.dosya)
    print(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str))
    return 0 if sonuc["durum"] == "tamam" else 1


if __name__ == "__main__":
    sys.exit(main())
