"""Kayıtlı run'larda bilinen karar hatalarını arayan denetim aracı.

Şu an tek kural: **son elde (1 el hakkı) discard hakkı varken, botun kendi hesabına göre discard daha yüksek
kazanma şansı verirken oynamak.** Bu kuralı ihlal eden her karar, run ve adımıyla listelenir.

    python -m balatro_ai.eval.denetim veri/10_planlayici_dar_v2-son-el-duzeltmeli
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from balatro_ai.data.okuma import baglan


def son_el_ihlalleri(klasor: str | Path) -> list[dict[str, Any]]:
    """Son elde, discard hakkı varken oynanan kararları tarar.

    İhlal: `son_el_arama` kaydı varsa discard'ın kazanma olasılığı oynamaktan yüksek olduğu halde oynanmış;
    kayıt yoksa (ajan son el aramasını yapmamış) ve oynanan el blind'ı bitirmemişse (kaybetme ihtimali) şüpheli.
    """
    con = baglan(klasor)
    satirlar = con.execute(
        """
        SELECT r.seed, d.adim,
          json_extract_string(d.komut, '$.yontem') AS yontem,
          json_extract(d.komut, '$.parametreler.cards') AS kartlar,
          CAST(json_extract_string(d.ham_durum, '$.round.discards_left') AS INTEGER) AS discard_hakki,
          json_extract_string(d.ek, '$.ajan.son_el_arama.oynayarak_kazanma') AS oyna_p,
          json_extract_string(d.ek, '$.ajan.son_el_arama.discard_ile_kazanma') AS discard_p,
          json_extract_string(d.cevap, '$.state') AS sonraki_faz
        FROM decisions d JOIN runs r USING (run_id)
        WHERE d.faz = 'SELECTING_HAND'
          AND json_extract_string(d.ham_durum, '$.round.hands_left') = '1'
          AND CAST(json_extract_string(d.ham_durum, '$.round.discards_left') AS INTEGER) > 0
          AND json_extract_string(d.komut, '$.yontem') = 'play'
        ORDER BY r.seed, d.adim
        """
    ).fetchall()
    ihlaller = []
    for seed, adim, _, kartlar, dh, oyna_p, discard_p, sonraki in satirlar:
        kaybetti = sonraki == "GAME_OVER" or sonraki == "SELECTING_HAND"  # blind bitmedi (el hakkı bitti ya da devam)
        if oyna_p is not None and discard_p is not None:
            ihlal = float(discard_p) > float(oyna_p)  # ajan kendi hesabına göre discard daha iyiyken oynadı
            neden = "discard_daha_iyiydi"
        else:
            ihlal = kaybetti  # arama kaydı yok ve kaybedildi: şüpheli
            neden = "arama_kaydi_yok_ve_kayip"
        if ihlal:
            ihlaller.append(
                {"seed": seed, "adim": adim, "kartlar": kartlar, "discard_hakki": dh, "oyna_p": oyna_p,
                 "discard_p": discard_p, "neden": neden}
            )
    return ihlaller


def main(argv: list[str] | None = None) -> int:
    """Komut satırı girişi: verilen klasörlerde son-el ihlallerini listeler; ihlal varsa 1 döndürür."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("klasorler", nargs="+")
    args = ap.parse_args(argv)
    toplam = 0
    for k in args.klasorler:
        ihlaller = son_el_ihlalleri(k)
        toplam += len(ihlaller)
        print(f"{k}: {len(ihlaller)} ihlal")
        for i in ihlaller:
            print("   ", i)
    return 1 if toplam else 0


if __name__ == "__main__":
    raise SystemExit(main())
