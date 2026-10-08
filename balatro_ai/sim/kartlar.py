"""Oyun kartı modeli ve oyundan (BalatroBot) gelen kartların çevrilmesi.

Değerler oyunun kendi Lua kodundan alınmıştır (game.lua P_CENTERS, card.lua), bkz. docs/PUAN_MOTORU.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Rütbe kimlikleri (Card:get_id): 2-10, J=11, Q=12, K=13, A=14.
RUTBE_ID = {r: i for i, r in enumerate("23456789TJQKA", start=2)}
# Kart başına temel chip değeri (base.nominal): 2-10 yüzey değeri, J/Q/K 10, A 11.
RUTBE_CHIP = {**{str(i): i for i in range(2, 10)}, "T": 10, "J": 10, "Q": 10, "K": 10, "A": 11}
# Aynı rütbede en yüksek kartı seçerken kullanılan ince sıralama (face_nominal, suit_nominal).
_YUZ = {"J": 0.1, "Q": 0.2, "K": 0.3, "A": 0.4}
_RENK_ONCELIK = {"D": 0.01, "C": 0.02, "H": 0.03, "S": 0.04}
RENKLER = ("S", "H", "C", "D")  # get_flush içindeki denetim sırası: Spades, Hearts, Clubs, Diamonds

GELISTIRMELER = frozenset({"bonus", "mult", "wild", "glass", "steel", "stone", "gold", "lucky"})
BASKILAR = frozenset({"foil", "holo", "polychrome", "negative"})
MUHURLER = frozenset({"red", "blue", "gold", "purple"})


@dataclass(frozen=True)
class Kart:
    """Oyun kartı: rütbe, renk ve isteğe bağlı geliştirme, baskı, mühür, kalıcı chip ve debuff."""
    rutbe: str  # "2".."9", "T", "J", "Q", "K", "A"
    renk: str  # "S", "H", "C", "D"
    gelistirme: str | None = None
    baski: str | None = None
    muhur: str | None = None
    kalici_chip: int = 0  # perma_bonus (ör. Hiker joker/tarot ile eklenen)
    debuff: bool = False

    def __post_init__(self) -> None:
        """Kartın alanlarının oyundaki geçerli değerlerden biri olduğunu doğrular."""
        if self.rutbe not in RUTBE_ID:
            raise ValueError(f"Bilinmeyen rütbe: {self.rutbe!r}")
        if self.renk not in RENKLER:
            raise ValueError(f"Bilinmeyen renk: {self.renk!r}")
        if self.gelistirme is not None and self.gelistirme not in GELISTIRMELER:
            raise ValueError(f"Bilinmeyen geliştirme: {self.gelistirme!r}")
        if self.baski is not None and self.baski not in BASKILAR:
            raise ValueError(f"Bilinmeyen baskı: {self.baski!r}")
        if self.muhur is not None and self.muhur not in MUHURLER:
            raise ValueError(f"Bilinmeyen mühür: {self.muhur!r}")

    @property
    def tas_mi(self) -> bool:
        """Kartın bir Stone kart olup olmadığı."""
        return self.gelistirme == "stone"

    @property
    def rutbe_id(self) -> int | None:
        """Stone kartın rütbesi yoktur (oyunda rastgele negatif sayı: hiçbir grupla eşleşmez)."""
        return None if self.tas_mi else RUTBE_ID[self.rutbe]

    def renk_uyar(self, renk: str) -> bool:
        """Flush denetimi: Wild her rengi sayar, Stone hiçbirini."""
        if self.tas_mi:
            return False
        return self.gelistirme == "wild" or self.renk == renk

    @property
    def chip(self) -> int:
        """Card:get_chip_bonus: yalnızca bu kartın taban + bonus chip'i (debuff 0)."""
        if self.debuff:
            return 0
        bonus = 30 if self.gelistirme == "bonus" else 50 if self.tas_mi else 0
        taban = 0 if self.tas_mi else RUTBE_CHIP[self.rutbe]
        return taban + bonus + self.kalici_chip

    @property
    def en_yuksek_anahtari(self) -> float:
        """get_highest için Card:get_nominal sıralaması (rütbe, sonra yüz kartı, sonra renk)."""
        if self.tas_mi:  # Stone: get_nominal'de çarpan -1000, hiçbir zaman en yüksek seçilmez
            return -1e9
        return RUTBE_CHIP[self.rutbe] + _YUZ.get(self.rutbe, 0.0) + _RENK_ONCELIK[self.renk]


def anahtardan(anahtar: str, **kw: Any) -> Kart:
    """"S_A" gibi oyun anahtarından düz (geliştirmesiz) kart."""
    renk, rutbe = anahtar.split("_")
    return Kart(rutbe=rutbe, renk=renk, **kw)


# BalatroBot `modifier` alanındaki değerler (büyük harf) -> bizim adlarımız.
_GELISTIRME_AD = {
    "BONUS": "bonus", "MULT": "mult", "WILD": "wild", "GLASS": "glass",
    "STEEL": "steel", "STONE": "stone", "GOLD": "gold", "LUCKY": "lucky",
}
_BASKI_AD = {"FOIL": "foil", "HOLO": "holo", "HOLOGRAPHIC": "holo", "POLYCHROME": "polychrome", "NEGATIVE": "negative"}
_MUHUR_AD = {"RED": "red", "BLUE": "blue", "GOLD": "gold", "PURPLE": "purple"}


def apiden(kart: dict[str, Any]) -> Kart:
    """BalatroBot kart sözlüğünden Kart. `modifier` biçimi gerçek oyunda geliştirilmiş kartlarla doğrulanmadı:
    bilinmeyen bir değer görülürse sessizce yok sayılmaz, hata verilir."""
    mod = kart.get("modifier") or {}
    durum = kart.get("state") or {}
    if not isinstance(mod, dict):
        mod = {}
    def sec(ad: str, tablo: dict[str, str]) -> str | None:
        """`modifier` sözlüğündeki bir alanı bizim adlarımıza çevirir; bilinmeyen değerde hata verir.
        """
        v = mod.get(ad)
        if v is None:
            return None
        if str(v).upper() not in tablo:
            raise ValueError(f"Bilinmeyen {ad}: {v!r}")
        return tablo[str(v).upper()]
    return anahtardan(
        kart["key"],
        gelistirme=sec("enhancement", _GELISTIRME_AD),
        baski=sec("edition", _BASKI_AD),
        muhur=sec("seal", _MUHUR_AD),
        debuff=bool(isinstance(durum, dict) and durum.get("debuff")),
    )
