"""Gezegen kartlarının değeri: bir el türünü yükseltmek, ortalama en iyi oynanışın skorunu ne kadar artırır?

Gezegen -> el türü eşlemesi oyunun `game.lua` dosyasındaki P_CENTERS tablosundan alınmıştır. Değer, destenin
rastgele 8 kartlık ellerinde (ortak örneklerle) "yükseltmeden önce" ve "sonra" en iyi oynanışın skoru farkıdır.
Discard ile el kovalamayı hesaba katmaz (en iyi oynanış hemen eldeki 8 karttan seçilir): çok sık çizilen
ama doğrudan gelmeyen eller (flush, straight) bu ölçüyle biraz düşük değerlenir.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from balatro_ai.sim.hizli import en_iyi_skor
from balatro_ai.sim.kartlar import Kart
from balatro_ai.sim.puan import EL_TABLOSU

# Gezegen kartı anahtarı -> yükselttiği el türü (oyunun tablosundan).
GEZEGEN_EL = {
    "c_pluto": "High Card",
    "c_mercury": "Pair",
    "c_uranus": "Two Pair",
    "c_venus": "Three of a Kind",
    "c_saturn": "Straight",
    "c_jupiter": "Flush",
    "c_earth": "Full House",
    "c_mars": "Four of a Kind",
    "c_neptune": "Straight Flush",
    "c_planet_x": "Five of a Kind",
    "c_ceres": "Flush House",
    "c_eris": "Flush Five",
}
# Mağaza ve paketlerde baştan çıkabilen 9 yaygın gezegen (diğer üçü, o el türü oynanana kadar gizlidir).
YAYGIN_GEZEGENLER = (
    "c_pluto", "c_mercury", "c_uranus", "c_venus", "c_saturn", "c_jupiter", "c_earth", "c_mars", "c_neptune",
)
# Gezegen paketleri: (kaç seçenek gösterilir, kaçı seçilir), anahtarın ikinci parçasına göre.
PAKET_SECENEKLERI = {"normal": (3, 1), "jumbo": (5, 1), "mega": (5, 2)}


def yukselt(el_degerleri: dict[str, tuple[float, float]], el_turu: str) -> dict[str, tuple[float, float]]:
    """El türünü bir seviye yükseltilmiş (chips, mult) tablosunu döndürür; girdiyi değiştirmez."""
    _, _, lc, lm = EL_TABLOSU[el_turu]
    c, m = el_degerleri.get(el_turu) or (float(EL_TABLOSU[el_turu][0]), float(EL_TABLOSU[el_turu][1]))
    return {**el_degerleri, el_turu: (c + lc, m + lm)}


def ornek_eller(deste: Sequence[Kart], ornek: int, rng: random.Random, el_boyu: int = 8) -> list[list[Kart]]:
    """Desteden `ornek` adet rastgele `el_boyu` kartlık el çeker (ortak örnek: tüm karşılaştırmalarda aynı eller)."""
    n = min(el_boyu, len(deste))
    return [rng.sample(list(deste), n) for _ in range(ornek)]


def gezegen_degerleri(
    eller: Sequence[Sequence[Kart]],
    el_degerleri: dict[str, tuple[float, float]],
    gezegenler: Sequence[str],
) -> dict[str, float]:
    """Her gezegen için, örnek ellerde el başına ortalama en iyi skor artışı (aynı örneklerle karşılaştırılır)."""
    taban = [en_iyi_skor(e, el_degerleri) for e in eller]
    sonuc: dict[str, float] = {}
    for g in gezegenler:
        yeni = yukselt(el_degerleri, GEZEGEN_EL[g])
        fark = sum(en_iyi_skor(e, yeni) - t for e, t in zip(eller, taban, strict=True))
        sonuc[g] = fark / len(eller)
    return sonuc


def paket_beklenen_degeri(
    degerler: dict[str, float], paket_turu: str, rng: random.Random, deneme: int = 2000
) -> float:
    """Bir gezegen paketinin beklenen değeri: gösterilen rastgele gezegenlerden en iyi `secilecek` kadarının toplam değeri.

    Gösterilen gezegenler yaygın 9 gezegenden rastgele ve tekrarsız seçilir (Monte Carlo).
    """
    gosterilen, secilecek = PAKET_SECENEKLERI[paket_turu]
    havuz = [degerler[g] for g in YAYGIN_GEZEGENLER if g in degerler]
    if not havuz:
        return 0.0
    k = min(gosterilen, len(havuz))
    toplam = 0.0
    for _ in range(deneme):
        secim = sorted(rng.sample(havuz, k), reverse=True)[:secilecek]
        toplam += sum(max(v, 0.0) for v in secim)
    return toplam / deneme
