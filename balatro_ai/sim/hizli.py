"""Düz kartlar (geliştirme/baskı/mühür/debuff yok, tekrarlı kart yok) için hızlı "en iyi el" hesabı.

Olasılık tahmininde (discard sonrası ortalama en iyi skor) on binlerce elin en iyi oynanışı gerekir; tam motor
(`puan.py`) bunun için çok yavaş. Bu modül elin en iyi skorunu, kombinasyonları denemek yerine el türüne göre
doğrudan hesaplar. Sonuç, düz kartlarda `max(puan_hesapla(altküme))` ile aynıdır (testlerle sınanır);
koşullar uymuyorsa `hizli_uygun_mu` yanlış döner ve çağıran tam motora geçmelidir.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import replace

from balatro_ai.sim import jokerler as joker_modulu
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


def en_iyi_oynanis(
    kartlar: Sequence[Kart],
    el_degerleri: dict[str, tuple[float, float]],
    chipler: Sequence[int] | None = None,
    jokerler: Sequence[joker_modulu.Joker] = (),
    baglam: joker_modulu.Baglam | None = None,
    yasak: frozenset[str] = frozenset(),
) -> tuple[int, tuple[int, ...]]:
    """En iyi oynanışın skorunu ve hangi kartlar (indeksler) olduğunu döndürür.

    `chipler`: kart başına chip değeri (debuff'lı kart 0); verilmezse rütbeden hesaplanır. Düz kartlar için
    `en_iyi_skor` ile aynı skoru verir; fazladan, oynanacak kartları da bildirir (puanlayan kartlar).

    Jokerlerle: skor puan.py ile aynı sırada (kart chip'i, kart başına joker etkileri, ana joker aşaması) hesaplanır. Hangi
    kartların seçileceği artık yalnızca chip'e değil, jokerlerin karta verdiği (chips, mult) değerlere de bağlıdır
    (ör. Walkie Talkie 4'lere +4 mult verir); bu yüzden her el türü için üç farklı kart sıralamasından aday denenir
    (chip, mult, ikisinin karması). Bu seçim sezgiseldir: skor hiçbir zaman tam motorun en iyisini aşmaz ama kaçırabilir.

    `yasak`: boss yüzünden 0 puan getiren el türleri (The Eye: bu turda oynanmış türler; The Mouth: ilk türün dışındakiler).
    Yasak türdeki oynanış 0 sayılır; hepsi yasaksa 0 puanlık bir oynanış döner.
    """
    n = len(kartlar)
    if n == 0:
        return 0, ()
    ids = [RUTBE_ID[k.rutbe] for k in kartlar]
    renkler = [RENK_INDEKS[k.renk] for k in kartlar]
    chip = list(chipler) if chipler is not None else [CHIP_ID[r] for r in ids]
    jokerler = list(jokerler)
    jb0 = baglam or joker_modulu.Baglam()
    dc = [0.0] * n
    dm = [0.0] * n
    if jokerler:
        for i, k in enumerate(kartlar):
            dc[i], dm[i] = joker_modulu.kart_vektoru(k, jokerler, jb0)
    # Kart sıralamaları (iyiden kötüye): jokersizde yalnızca chip; jokerlide chip, mult ve karışımı.
    anahtarlar = [lambda i: chip[i] + dc[i]]
    if jokerler:
        anahtarlar += [lambda i: (dm[i], chip[i] + dc[i]), lambda i: (chip[i] + dc[i]) * (1.0 + dm[i] / 4.0)]

    def en_iyiler(indeksler: Sequence[int], k: int) -> list[tuple[int, ...]]:
        """Verilen indekslerden, her sıralamaya göre en iyi `k` kartlık farklı seçimler."""
        sonuc: list[tuple[int, ...]] = []
        for anahtar in anahtarlar:
            secim = tuple(sorted(sorted(indeksler, key=anahtar, reverse=True)[:k]))
            if secim not in sonuc:
                sonuc.append(secim)
        return sonuc

    gruplar: dict[int, list[int]] = {}
    for i, r in enumerate(ids):
        gruplar.setdefault(r, []).append(i)
    for g in gruplar.values():  # grup içinde chip'i yüksek kart önce (jokersiz yol bunu kullanır)
        g.sort(key=lambda i: chip[i], reverse=True)

    en_skor, en_idx = 0.0, ()

    def aday(tur: str, idx: tuple[int, ...]) -> None:
        """Bir el türü ve kart indeksi adayının skorunu hesaplayıp şu ana kadarki en iyisiyle karşılaştırır."""
        nonlocal en_skor, en_idx
        c, m = el_degerleri.get(tur) or (float(EL_TABLOSU[tur][0]), float(EL_TABLOSU[tur][1]))
        if tur in yasak:  # boss bu türü sıfırlıyor
            if not en_idx:
                en_idx = idx
            return
        if jokerler:  # kart kart, joker sırasıyla (puan.py ile aynı sıra): kart chip'i, kart başına etkiler, sonra ana aşama
            jb = replace(
                jb0, el_turu=tur, iceren=frozenset(joker_modulu.ICEREN[tur]), oynanan_sayisi=len(idx),
                joker_sayisi=len(jokerler),
            )
            ch, mu = c, m
            for i in sorted(idx):
                ch += chip[i]
                ch, mu = joker_modulu.kart_basina_uygula(ch, mu, kartlar[i], jokerler, jb)
            ch, mu = joker_modulu.ana_uygula(ch, mu, jokerler, jb)
            s = math.floor(ch * mu)
        else:
            s = (c + sum(chip[i] for i in idx)) * m
        if s > en_skor or not en_idx:
            en_skor, en_idx = s, idx

    if jokerler:  # her tek kart: jokerler karta çok farklı değer verebilir
        for i in range(n):
            aday("High Card", (i,))
    else:
        aday("High Card", (max(range(n), key=lambda i: chip[i]),))
    gruplu = [(r, g) for r, g in gruplar.items()]
    ciftler: list[tuple[int, tuple[int, ...]]] = []  # (rütbe, seçilen kartlar) tüm çiftler ve seçim varyantları
    ucluler: list[tuple[int, tuple[int, ...]]] = []
    for r, g in gruplu:
        if len(g) >= 2:
            for secim in en_iyiler(g, 2):
                ciftler.append((r, secim))
                aday("Pair", secim)
        if len(g) >= 3:
            for secim in en_iyiler(g, 3):
                ucluler.append((r, secim))
                aday("Three of a Kind", secim)
        if len(g) >= 4:
            for secim in en_iyiler(g, 4):
                aday("Four of a Kind", secim)
    if jokerler:  # her iki çift grubu ve tüm seçim varyantları
        for (r1, s1), (r2, s2) in itertools.combinations(ciftler, 2):
            if r1 != r2:
                aday("Two Pair", s1 + s2)
        for r1, s1 in ucluler:
            for r2, s2 in ciftler:
                if r1 != r2:
                    aday("Full House", s1 + s2)
    else:
        ciftler.sort(key=lambda x: sum(chip[i] for i in x[1]), reverse=True)
        farkli = []
        for r, s in ciftler:
            if all(r != r0 for r0, _ in farkli):
                farkli.append((r, s))
        if len(farkli) >= 2:
            aday("Two Pair", farkli[0][1] + farkli[1][1])
        en_fh = None
        for rt, st in ucluler:
            for rp, sp in farkli:
                if rp != rt:
                    toplam = sum(chip[i] for i in st + sp)
                    if en_fh is None or toplam > en_fh[0]:
                        en_fh = (toplam, st + sp)
        if en_fh:
            aday("Full House", en_fh[1])
    for rk in range(4):  # Flush: aynı renkli kartlardan en iyi 5
        ayni = [i for i in range(n) if renkler[i] == rk]
        if len(ayni) >= 5:
            for secim in en_iyiler(ayni, 5):
                aday("Flush", secim)
    for alt in range(1, 11):  # Straight / Straight Flush: 5 ardışık rütbe
        pencere = [14 if x == 1 else x for x in range(alt, alt + 5)]
        if all(p in gruplar for p in pencere):
            for anahtar in anahtarlar:
                aday("Straight", tuple(max(gruplar[p], key=anahtar) for p in pencere))
            for rk in range(4):
                secim = []
                for p in pencere:
                    k = next((i for i in gruplar[p] if renkler[i] == rk), None)
                    if k is None:
                        break
                    secim.append(k)
                else:
                    aday("Straight Flush", tuple(secim))
    return int(en_skor), tuple(sorted(en_idx))
