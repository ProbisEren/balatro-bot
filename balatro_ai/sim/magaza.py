"""Mağaza değerlendirmesi: bir satın almanın, sonraki blind'ları geçme ihtimaline etkisi (rollout ile).

Değer birimi "beklenen geçilen blind sayısı" (sonraki K blind'ın geçilme olasılıklarının toplamı). Bir öğe, el değerlerini
(gezegen), oynanış kurallarını (joker) veya kart özelliklerini (tarot) değiştirir; değeri, değişiklikten önceki ve sonraki
beklenen geçilen blind sayısı farkıdır. Karşılaştırma ortak rastgele desteler üzerinde yapılır (aynı şans, yalnızca öğe farkı).

Para modeli: bir öğenin maliyeti fiyatı artı kaybedilen faizdir (bir sonraki K turda, her $5 için $1, en çok $5 faiz).
Paranın başka bir değeri (ileride alınacak şeyler) `PARA_DEGERI` ile tahmin edilir: ayarlanmamış bir tahmindir.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from balatro_ai.sim.jokerler import Baglam, Joker
from balatro_ai.sim.kartlar import Kart
from balatro_ai.sim.tur import Tur, rollout

PARA_DEGERI = 0.02  # 1 dolarlık maliyetin "geçilen blind" cinsinden değeri (TAHMİN, deneyle ayarlanacak)
SONRAKI_BLIND = 3  # değerlendirmede bakılan blind sayısı
DUNYA = 40  # her blind için ortak rastgele deste sayısı


def faiz(para: int) -> int:
    """Oyunun faizi: tur sonunda her 5 dolar için 1 dolar, en çok 5 dolar."""
    return min(max(para, 0) // 5, 5)


def faiz_kaybi(para: int, fiyat: int, tur_sayisi: int = SONRAKI_BLIND) -> int:
    """Bir harcamanın, önümüzdeki `tur_sayisi` turda kaybettireceği toplam faiz."""
    return (faiz(para) - faiz(para - fiyat)) * tur_sayisi


def maliyet(para: int, fiyat: int) -> float:
    """Bir satın almanın "geçilen blind" cinsinden maliyeti: (fiyat + kaybedilen faiz) x paranın değeri."""
    return (fiyat + faiz_kaybi(para, fiyat)) * PARA_DEGERI


def desteler_uret(deste: Sequence[Kart], hedef_sayisi: int, rng: random.Random, dunya: int = DUNYA) -> list[list[list[Kart]]]:
    """Her blind için `dunya` adet karışık deste üretir (ortak rastgelelik: tüm yapılandırmalar aynı desteleri görür)."""
    sonuc = []
    for _ in range(hedef_sayisi):
        liste = []
        for _ in range(dunya):
            d = list(deste)
            rng.shuffle(d)
            liste.append(d)
        sonuc.append(liste)
    return sonuc


def gecme_orani(
    desteler: Sequence[Sequence[Kart]], el_degerleri: dict[str, tuple[float, float]], hedef: float,
    el_hakki: int, discard_hakki: int, el_boyu: int = 8, tohum: int = 0,
    jokerler: Sequence[Joker] = (), baglam: Baglam | None = None,
) -> float:
    """Verilen el değerleri ve jokerlerle, bir blind'ı temel politikayla geçme oranı (aynı desteler üzerinde)."""
    gecen = 0
    for j, d in enumerate(desteler):
        t = Tur([], list(d), el_hakki, discard_hakki, 0.0, float(hedef), el_degerleri, el_boyu,
                jokerler=tuple(jokerler), baglam=baglam or Baglam())
        t.doldur()
        rollout(t, random.Random(tohum * 1000 + j))
        gecen += t.kazandi()
    return gecen / len(desteler)


def beklenen_gecilen_blind(
    desteler: Sequence[Sequence[Sequence[Kart]]], el_degerleri: dict[str, tuple[float, float]],
    hedefler: Sequence[float | Sequence[tuple[float, float]]], el_hakki: int, discard_hakki: int, el_boyu: int = 8,
    jokerler: Sequence[Joker] = (), baglam: Baglam | None = None,
) -> float:
    """Sonraki blind'ların geçilme olasılıkları toplamı (blind başına ayrı destelerle).

    Her blind ya tek bir hedef sayısı ya da (hedef, olasılık) karışımıdır (bilinmeyen boss için); karışımda geçilme
    olasılığı hedeflerin olasılık ağırlıklı ortalamasıdır. Jokerler her turda elde taşınıyormuş gibi simüle edilir.
    """
    toplam = 0.0
    for k, h in enumerate(hedefler):
        karisim = [(float(h), 1.0)] if isinstance(h, int | float) else list(h)
        toplam += sum(
            w * gecme_orani(desteler[k], el_degerleri, hedef, el_hakki, discard_hakki, el_boyu, tohum=k,
                            jokerler=jokerler, baglam=baglam)
            for hedef, w in karisim
        )
    return toplam


# game.lua `get_blind_amount`: stake'e göre ante 1-8 taban hedefler (ölçekleme 1: stake < 3; 2: stake >= 3; 3: stake >= 6).
# Beyaz stake (ölçekleme 1) gözlemle doğrulandı: ante 1 = 300, ante 2 = 800. Diğer ikisi oyunun kodundan okundu, doğrulanmadı.
ANTE_TABANLARI = {
    1: (300, 800, 2000, 5000, 11000, 20000, 35000, 50000),
    2: (300, 900, 2600, 8000, 20000, 36000, 60000, 100000),
    3: (300, 1000, 3200, 9000, 25000, 60000, 110000, 200000),
}
STAKE_SIRASI = ("WHITE", "RED", "GREEN", "BLACK", "BLUE", "PURPLE", "ORANGE", "GOLD")  # BalatroBot enum sırası = oyundaki stake numarası - 1
BLIND_CARPAN = {"small": 1.0, "big": 1.5}

# game.lua P_BLINDS: boss -> (hedef çarpanı, ilk çıkabileceği ante, showdown mu). Showdown bosslar yalnızca 8, 16... ante'lerinde çıkar.
BOSSLAR = {
    "The Ox": (2, 6, False), "The Hook": (2, 1, False), "The Mouth": (2, 2, False), "The Fish": (2, 2, False),
    "The Club": (2, 1, False), "The Manacle": (2, 1, False), "The Tooth": (2, 3, False), "The Wall": (4, 2, False),
    "The House": (2, 2, False), "The Mark": (2, 2, False), "The Wheel": (2, 2, False), "The Arm": (2, 2, False),
    "The Psychic": (2, 1, False), "The Goad": (2, 1, False), "The Water": (2, 2, False), "The Eye": (2, 3, False),
    "The Plant": (2, 4, False), "The Needle": (1, 2, False), "The Head": (2, 1, False), "The Window": (2, 1, False),
    "The Serpent": (2, 5, False), "The Pillar": (2, 1, False), "The Flint": (2, 2, False),
    "Cerulean Bell": (2, 8, True), "Verdant Leaf": (2, 8, True), "Violet Vessel": (6, 8, True),
    "Amber Acorn": (2, 8, True), "Crimson Heart": (2, 8, True),
}


def olcekleme(stake: str | int | None) -> int:
    """Stake adından (veya numarasından, 1 = WHITE) hedef ölçekleme tablosu numarası (1, 2 veya 3)."""
    no = stake if isinstance(stake, int) else (STAKE_SIRASI.index(stake) + 1 if stake in STAKE_SIRASI else 1)
    return 3 if no >= 6 else 2 if no >= 3 else 1


def boss_carpan_dagilimi(ante: int) -> list[tuple[float, float]]:
    """Henüz bilinmeyen bir ante'nin bossu için (hedef çarpanı, olasılık) karışımı: o ante'de çıkabilecek bosslar eşit olasılıklı."""
    showdown = ante % 8 == 0
    uygun = [c for c, ilk, sd in BOSSLAR.values() if sd == showdown and ilk <= ante or (showdown and sd)]
    if not uygun:
        return [(2.0, 1.0)]
    sayac: dict[float, int] = {}
    for c in uygun:
        sayac[float(c)] = sayac.get(float(c), 0) + 1
    return sorted((c, n / len(uygun)) for c, n in sayac.items())


def sonraki_hedefler(
    blinds: dict, ante: int, adet: int = SONRAKI_BLIND, stake: str | int | None = "WHITE"
) -> list[list[tuple[float, float]]]:
    """Mağazadan sonra gelecek blind'ların hedefleri; her blind için (hedef, olasılık) karışımı.

    Ekranda görünen (henüz geçilmemiş/atlanmamış) blind'ların gerçek hedefleri kesin (olasılık 1) kullanılır. Yetmezse bir sonraki
    ante'nin blind'ları stake'in taban tablosundan hesaplanır: small 1x, big 1,5x, boss için henüz bilinmediğinden olası boss
    çarpanlarının karışımı (çoğunlukla 2x; The Needle 1x, The Wall 4x, showdown'da bazen 6x).
    """
    hedefler: list[list[tuple[float, float]]] = [
        [(float(blinds[ad]["score"]), 1.0)] for ad in ("small", "big", "boss")
        if ad in blinds and blinds[ad].get("status") in ("SELECT", "UPCOMING", "CURRENT") and blinds[ad].get("score")
    ]
    tablo = ANTE_TABANLARI[olcekleme(stake)]
    a = ante
    while len(hedefler) < adet:
        a += 1
        taban = tablo[min(a, len(tablo)) - 1]
        hedefler += [[(taban * BLIND_CARPAN["small"], 1.0)], [(taban * BLIND_CARPAN["big"], 1.0)]]
        hedefler.append([(taban * c, w) for c, w in boss_carpan_dagilimi(a)])
    return hedefler[:adet]
