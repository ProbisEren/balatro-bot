"""Boss blind'lerin puanlamaya etkileri (oyunun blind.lua dosyasından).

Kart düzeyi (`Blind:debuff_card`): bir suit'i, yüz kartlarını veya (Verdant Leaf) tüm kartları debuff'lar.
El düzeyi (`Blind:debuff_hand`): The Psychic 5'ten az kartı, The Eye daha önce oynanan türü, The Mouth
ilk türden başkasını sıfır puanlar. Taban değişimi (`Blind:modify_hand`): The Flint taban chips ve mult'ı
yarıya indirir. The Arm, oynanan türün seviyesini puanlamadan önce 1 düşürür (seviye > 1 ise).

Uygulanmayanlar (puanlamayı değiştirmez ya da geçmiş/rastgelelik gerektirir): The Pillar (önceki oynanan
kartlar; oyun `state.debuff` ile zaten bildirir), The Hook, The House, The Wheel, The Fish, The Mark,
The Serpent, The Manacle, The Needle, The Water, The Wall/Violet Vessel (hedefi etkiler, skoru değil),
Amber Acorn, Crimson Heart, Cerulean Bell, The Ox, The Tooth.
"""

from __future__ import annotations

from dataclasses import replace

from balatro_ai.sim.kartlar import Kart

RENK_BOSS = {"The Club": "C", "The Goad": "S", "The Window": "D", "The Head": "H"}
YUZ_RUTBELERI = frozenset("JQK")


def kart_debuff_mi(boss: str | None, kart: Kart) -> bool:
    """Verilen boss blind'in bu kartı debuff'layıp debuff'lamadığı (renk, yüz kartı, Verdant Leaf).
    """
    if boss is None:
        return False
    if boss == "Verdant Leaf":
        return True
    if boss in RENK_BOSS:
        return not kart.tas_mi and (kart.gelistirme == "wild" or kart.renk == RENK_BOSS[boss])
    if boss == "The Plant":
        return not kart.tas_mi and kart.rutbe in YUZ_RUTBELERI
    return False


def kartlara_uygula(boss: str | None, kartlar: list[Kart]) -> list[Kart]:
    """Boss kuralına göre debuff'lanması gereken kartları işaretler (zaten debuff'lı olanlar korunur)."""
    return [replace(k, debuff=True) if (not k.debuff and kart_debuff_mi(boss, k)) else k for k in kartlar]


def el_debuff_mi(
    boss: str | None,
    oynanan_sayisi: int,
    el_turu: str,
    gecmis_turler: frozenset[str] = frozenset(),
    ilk_tur: str | None = None,
) -> bool:
    """Boss blind'in bu eli tamamen sıfır puanlayıp puanlamadığı (Psychic, Eye, Mouth)."""
    if boss == "The Psychic":
        return oynanan_sayisi < 5
    if boss == "The Eye":
        return el_turu in gecmis_turler
    if boss == "The Mouth":
        return ilk_tur is not None and ilk_tur != el_turu
    return False


def taban_degistir(boss: str | None, chips: float, mult: float) -> tuple[float, float]:
    """`Blind:modify_hand`: The Flint taban değerleri yarıya indirir (yukarı yuvarlayarak)."""
    if boss == "The Flint":
        return max(float(int(chips * 0.5 + 0.5)), 0.0), max(float(int(mult * 0.5 + 0.5)), 1.0)
    return chips, mult
