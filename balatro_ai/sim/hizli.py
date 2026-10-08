"""Düz kartlar (geliştirme/baskı/mühür/debuff yok, tekrarlı kart yok) için hızlı "en iyi el" hesabı.

Olasılık tahmininde (discard sonrası ortalama en iyi skor) on binlerce elin en iyi oynanışı gerekir; tam motor
(`puan.py`) bunun için çok yavaş. Bu modül elin en iyi skorunu, kombinasyonları denemek yerine el türüne göre
doğrudan hesaplar. Sonuç, düz kartlarda `max(puan_hesapla(altküme))` ile aynıdır (testlerle sınanır);
koşullar uymuyorsa `hizli_uygun_mu` yanlış döner ve çağıran tam motora geçmelidir.
"""

from __future__ import annotations

from collections.abc import Sequence

from balatro_ai.sim.kartlar import RENKLER, RUTBE_CHIP, RUTBE_ID, Kart
from balatro_ai.sim.puan import EL_TABLOSU

RENK_INDEKS = {r: i for i, r in enumerate(RENKLER)}
CHIP_ID = {RUTBE_ID[r]: c for r, c in RUTBE_CHIP.items()}  # rütbe kimliği -> chip


def hizli_uygun_mu(kartlar: Sequence[Kart]) -> bool:
    """Kartlar hızlı hesaplayıcıya uygun mu: geliştirme, baskı, mühür, debuff ve tekrarlı kart yok.
    """
    gorulen: set[tuple[str, str]] = set()
    for k in kartlar:
        if k.gelistirme or k.baski or k.muhur or k.debuff or k.kalici_chip:
            return False
        if (k.rutbe, k.renk) in gorulen:
            return False
        gorulen.add((k.rutbe, k.renk))
    return True


def en_iyi_skor(kartlar: Sequence[Kart], el_degerleri: dict[str, tuple[float, float]]) -> int:
    """`kartlar` içinden oynanabilecek (1-5 kart) en yüksek skor. `el_degerleri`: tür -> (chips, mult)."""
    ids = [RUTBE_ID[k.rutbe] for k in kartlar]
    renkler = [RENK_INDEKS[k.renk] for k in kartlar]
    sayi: dict[int, int] = {}
    for r in ids:
        sayi[r] = sayi.get(r, 0) + 1

    def deger(tur: str) -> tuple[float, float]:
        """Bir el türünün (chips, mult) değeri; verilmemişse oyunun seviye 1 tablosu."""
        return el_degerleri.get(tur) or (float(EL_TABLOSU[tur][0]), float(EL_TABLOSU[tur][1]))

    en = 0.0

    def aday(tur: str, chip_toplami: int) -> None:
        """Bir el türü adayının skorunu hesaplayıp şu ana kadarki en iyisiyle karşılaştırır."""
        nonlocal en
        c, m = deger(tur)
        s = (c + chip_toplami) * m
        en = max(en, s)

    # Yüksek kart: en yüksek rütbe tek kart.
    aday("High Card", CHIP_ID[max(ids)])
    # Aynı rütbe grupları (rütbe, chip), chip'e göre büyükten küçüğe.
    for adet_min, tur, adet in ((2, "Pair", 2), (3, "Three of a Kind", 3), (4, "Four of a Kind", 4)):
        uygun = [CHIP_ID[r] for r, n in sayi.items() if n >= adet_min]
        if uygun:
            aday(tur, adet * max(uygun))
    ciftler = sorted((CHIP_ID[r] for r, n in sayi.items() if n >= 2), reverse=True)
    if len(ciftler) >= 2:
        aday("Two Pair", 2 * ciftler[0] + 2 * ciftler[1])
    uclu = [r for r, n in sayi.items() if n >= 3]
    if uclu and len([r for r, n in sayi.items() if n >= 2]) >= 2:
        en_fh = 0
        for t in uclu:
            for p, n in sayi.items():
                if p != t and n >= 2:
                    en_fh = max(en_fh, 3 * CHIP_ID[t] + 2 * CHIP_ID[p])
        aday("Full House", en_fh)
    # Flush: tam 5 kart (elde 5'ten fazla aynı renk varsa en yüksek chip'li 5).
    flush_renkleri = [rk for rk in range(4) if renkler.count(rk) >= 5]
    for rk in flush_renkleri:
        chipler = sorted((CHIP_ID[r] for r, c in zip(ids, renkler, strict=True) if c == rk), reverse=True)
        aday("Flush", sum(chipler[:5]))
    # Straight ve Straight Flush: 5 ardışık rütbe (As hem düşük hem yüksek).
    mevcut = set(sayi)
    renk_rutbe = [{r for r, c in zip(ids, renkler, strict=True) if c == rk} for rk in range(4)]
    for alt in range(1, 11):  # 1 = As düşük
        pencere = [14 if x == 1 else x for x in range(alt, alt + 5)]
        if all(p in mevcut for p in pencere):
            toplam = sum(CHIP_ID[p] for p in pencere)
            aday("Straight", toplam)
            if any(all(p in rr for p in pencere) for rr in renk_rutbe):
                aday("Straight Flush", toplam)
    return int(en)  # skor chips*mult'un tabanı (düz kartlarda tamsayı)
