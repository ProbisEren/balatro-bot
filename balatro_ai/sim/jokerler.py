"""Joker etkileri: oyunun `card.lua` (`Card:calculate_joker`) ve `game.lua` (P_CENTERS) dosyalarından okunan kurallar.

Her jokerin sayıları ve koşulları oyunun kendi dosyalarından alınmıştır (hafızadan değil); yalnızca bu dosyada tanımlı
jokerler "desteklenir". Desteklenmeyen bir jokerle skor hesaplamak yanlış sonuç verir, bu yüzden `puan_hesapla` bilinmeyen
joker görürse hata verir, ajan da etkisi bilinmeyen jokeri satın almaz.

İki tür etki vardır (oyundaki sıra):
  kart başına  : oynanan her puanlayan kart için, kartın kendi etkisinden SONRA, jokerler soldan sağa (+chips, +mult, x mult)
  ana          : tüm kartlar ve eldeki kartlardan sonra, jokerler soldan sağa. Her joker için sırayla: baskı (Foil +50 chips,
                 Holo +10 mult), jokerin kendi etkisi (+mult, +chips, sonra x mult), en sonda Polychrome x1.5
Bir etki `(chips, mult, çarpan)` üçlüsüdür; uygulanışı: chips += c; mult = (mult + m) * çarpan.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from balatro_ai.sim.kartlar import RUTBE_ID, Kart

Etki = tuple[float, float, float]
ETKISIZ: Etki = (0.0, 0.0, 1.0)

# Bir el türünün içerdiği türler (oyunun evaluate_poker_hand sonundaki türetme; fazladan kart yokken).
ICEREN = {
    "High Card": {"High Card"},
    "Pair": {"Pair", "High Card"},
    "Two Pair": {"Two Pair", "Pair", "High Card"},
    "Three of a Kind": {"Three of a Kind", "Pair", "High Card"},
    "Straight": {"Straight", "High Card"},
    "Flush": {"Flush", "High Card"},
    "Full House": {"Full House", "Three of a Kind", "Two Pair", "Pair", "High Card"},
    "Four of a Kind": {"Four of a Kind", "Three of a Kind", "Pair", "High Card"},
    "Straight Flush": {"Straight Flush", "Straight", "Flush", "High Card"},
    "Five of a Kind": {"Five of a Kind", "Four of a Kind", "Three of a Kind", "Pair", "High Card"},
    "Flush House": {"Flush House", "Full House", "Flush", "Three of a Kind", "Two Pair", "Pair", "High Card"},
    "Flush Five": {
        "Flush Five", "Five of a Kind", "Four of a Kind", "Three of a Kind", "Pair", "Flush", "High Card",
    },
}
RENK_ADI = {"Diamonds": "D", "Hearts": "H", "Spades": "S", "Clubs": "C"}
YUZ = frozenset("JQK")


@dataclass(frozen=True)
class Baglam:
    """Skor anında jokerlerin baktığı oyun bilgisi (oynanışla ilgili sayaçlar, haklar, para)."""

    el_turu: str = "High Card"
    iceren: frozenset[str] = frozenset()
    oynanan_sayisi: int = 5  # oynanan kart sayısı (puanlamayanlar dahil)
    kalan_discard: int = 0  # puanlama anında kalan discard hakkı
    kalan_el: int = 0  # puanlama anında kalan el hakkı (oynanan el düşüldükten sonra)
    joker_sayisi: int = 0  # elde taşınan joker sayısı
    deste_boyu: int = 0  # çekme destesinde kalan kart sayısı (Blue Joker)
    para: int = 0
    # El türü -> (bu run'da oynanma, bu turda oynanma), şimdiki oynanıştan ÖNCE (oyun durumundaki `hands[tür].played`).
    sayaclar: Mapping[str, tuple[int, int]] = field(default_factory=dict, hash=False, compare=False)

    @property
    def oynanma(self) -> int:
        """Bu el türünün bu run'da oynanma sayısı, şimdiki oynanış dahil (oyun puanlamadan önce sayacı artırır; Supernova)."""
        return self.sayaclar.get(self.el_turu, (0, 0))[0] + 1

    @property
    def bu_turda_oynanma(self) -> int:
        """Bu el türünün bu turda oynanma sayısı, şimdiki oynanış dahil (Card Sharp)."""
        return self.sayaclar.get(self.el_turu, (0, 0))[1] + 1


@dataclass(frozen=True)
class Joker:
    """Elde taşınan bir joker: anahtarı (`j_joker`) ve isteğe bağlı baskısı (foil, holo, polychrome, negative)."""

    key: str
    baski: str | None = None
    durum: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)  # ölçeklenen jokerlerin anlık değerleri (henüz kullanılmıyor)


@dataclass(frozen=True)
class Tanim:
    """Bir jokerin oyun kuralı: kart başına etkisi ve/veya ana etkisi."""

    ad: str
    kart_basina: Callable[[Kart, Baglam], Etki] | None = None
    ana: Callable[[Baglam], Etki] | None = None
    belirsiz: bool = False  # etkisi rastgele (Misprint): skor kesin değil, beklenen değer kullanılır


def _renk_mi(kart: Kart, renk: str) -> bool:
    """Kartın o rengi sayıp saymadığı (Wild her rengi sayar, Stone ve debuff'lı kart hiçbirini)."""
    return not kart.debuff and not kart.tas_mi and (kart.gelistirme == "wild" or kart.renk == renk)


def _yuz_mu(kart: Kart) -> bool:
    """Kart bir yüz kartı mı (J, Q, K); debuff'lı ve Stone kartlar sayılmaz."""
    return not kart.debuff and not kart.tas_mi and kart.rutbe in YUZ


def _id(kart: Kart) -> int | None:
    """Kartın rütbe kimliği (2-14); debuff'lı veya Stone kartta None (Card:get_id Stone için rastgele negatif sayı)."""
    return None if kart.debuff or kart.tas_mi else RUTBE_ID[kart.rutbe]


def _suit_joker(renk_adi: str, mult: float) -> Callable[[Kart, Baglam], Etki]:
    """Suit Mult jokeri: o renkteki her puanlayan kart için +mult."""
    harf = RENK_ADI[renk_adi]
    return lambda k, b: (0.0, mult, 1.0) if _renk_mi(k, harf) else ETKISIZ


def _tur_mult(tur: str, mult: float) -> Callable[[Baglam], Etki]:
    """El türünü içeriyorsa +mult (Jolly, Zany, Mad, Crazy, Droll)."""
    return lambda b: (0.0, mult, 1.0) if tur in b.iceren else ETKISIZ


def _tur_chips(tur: str, chips: float) -> Callable[[Baglam], Etki]:
    """El türünü içeriyorsa +chips (Sly, Wily, Clever, Devious, Crafty)."""
    return lambda b: (chips, 0.0, 1.0) if tur in b.iceren else ETKISIZ


def _tur_carpan(tur: str, carpan: float) -> Callable[[Baglam], Etki]:
    """El türünü içeriyorsa x mult (The Duo, Trio, Family, Order, Tribe)."""
    return lambda b: (0.0, 0.0, carpan) if tur in b.iceren else ETKISIZ


def _kart_kimlik(kosul: Callable[[int], bool], etki: Etki) -> Callable[[Kart, Baglam], Etki]:
    """Kartın rütbe kimliği koşulu sağlıyorsa verilen etkiyi veren kart-başına işlev."""
    return lambda k, b: etki if (i := _id(k)) is not None and kosul(i) else ETKISIZ


# game.lua P_CENTERS config değerleri ve card.lua calculate_joker koşulları (okunarak yazıldı).
TANIMLAR: dict[str, Tanim] = {
    "j_joker": Tanim("Joker", ana=lambda b: (0.0, 4.0, 1.0)),
    "j_greedy_joker": Tanim("Greedy Joker", kart_basina=_suit_joker("Diamonds", 3)),
    "j_lusty_joker": Tanim("Lusty Joker", kart_basina=_suit_joker("Hearts", 3)),
    "j_wrathful_joker": Tanim("Wrathful Joker", kart_basina=_suit_joker("Spades", 3)),
    "j_gluttenous_joker": Tanim("Gluttonous Joker", kart_basina=_suit_joker("Clubs", 3)),
    "j_jolly": Tanim("Jolly Joker", ana=_tur_mult("Pair", 8)),
    "j_zany": Tanim("Zany Joker", ana=_tur_mult("Three of a Kind", 12)),
    "j_mad": Tanim("Mad Joker", ana=_tur_mult("Two Pair", 10)),
    "j_crazy": Tanim("Crazy Joker", ana=_tur_mult("Straight", 12)),
    "j_droll": Tanim("Droll Joker", ana=_tur_mult("Flush", 10)),
    "j_sly": Tanim("Sly Joker", ana=_tur_chips("Pair", 50)),
    "j_wily": Tanim("Wily Joker", ana=_tur_chips("Three of a Kind", 100)),
    "j_clever": Tanim("Clever Joker", ana=_tur_chips("Two Pair", 80)),
    "j_devious": Tanim("Devious Joker", ana=_tur_chips("Straight", 100)),
    "j_crafty": Tanim("Crafty Joker", ana=_tur_chips("Flush", 80)),
    "j_half": Tanim("Half Joker", ana=lambda b: (0.0, 20.0, 1.0) if b.oynanan_sayisi <= 3 else ETKISIZ),
    "j_banner": Tanim("Banner", ana=lambda b: (30.0 * b.kalan_discard, 0.0, 1.0) if b.kalan_discard > 0 else ETKISIZ),
    "j_mystic_summit": Tanim("Mystic Summit", ana=lambda b: (0.0, 15.0, 1.0) if b.kalan_discard == 0 else ETKISIZ),
    "j_misprint": Tanim("Misprint", ana=lambda b: (0.0, 11.5, 1.0), belirsiz=True),  # 0-23 arası rastgele: beklenen değer
    "j_abstract": Tanim("Abstract Joker", ana=lambda b: (0.0, 3.0 * b.joker_sayisi, 1.0)),
    "j_gros_michel": Tanim("Gros Michel", ana=lambda b: (0.0, 15.0, 1.0)),
    "j_cavendish": Tanim("Cavendish", ana=lambda b: (0.0, 0.0, 3.0)),
    "j_blue_joker": Tanim("Blue Joker", ana=lambda b: (2.0 * b.deste_boyu, 0.0, 1.0) if b.deste_boyu > 0 else ETKISIZ),
    "j_supernova": Tanim("Supernova", ana=lambda b: (0.0, float(b.oynanma), 1.0)),
    "j_card_sharp": Tanim("Card Sharp", ana=lambda b: (0.0, 0.0, 3.0) if b.bu_turda_oynanma > 1 else ETKISIZ),
    "j_acrobat": Tanim("Acrobat", ana=lambda b: (0.0, 0.0, 3.0) if b.kalan_el == 0 else ETKISIZ),
    "j_duo": Tanim("The Duo", ana=_tur_carpan("Pair", 2)),
    "j_trio": Tanim("The Trio", ana=_tur_carpan("Three of a Kind", 3)),
    "j_family": Tanim("The Family", ana=_tur_carpan("Four of a Kind", 4)),
    "j_order": Tanim("The Order", ana=_tur_carpan("Straight", 3)),
    "j_tribe": Tanim("The Tribe", ana=_tur_carpan("Flush", 2)),
    "j_fibonacci": Tanim("Fibonacci", kart_basina=_kart_kimlik(lambda i: i in (2, 3, 5, 8, 14), (0.0, 8.0, 1.0))),
    "j_scary_face": Tanim("Scary Face", kart_basina=lambda k, b: (30.0, 0.0, 1.0) if _yuz_mu(k) else ETKISIZ),
    "j_smiley": Tanim("Smiley Face", kart_basina=lambda k, b: (0.0, 5.0, 1.0) if _yuz_mu(k) else ETKISIZ),
    "j_even_steven": Tanim("Even Steven", kart_basina=_kart_kimlik(lambda i: i <= 10 and i % 2 == 0, (0.0, 4.0, 1.0))),
    "j_odd_todd": Tanim("Odd Todd", kart_basina=_kart_kimlik(lambda i: (i <= 10 and i % 2 == 1) or i == 14, (31.0, 0.0, 1.0))),
    "j_scholar": Tanim("Scholar", kart_basina=_kart_kimlik(lambda i: i == 14, (20.0, 4.0, 1.0))),
    "j_walkie_talkie": Tanim("Walkie Talkie", kart_basina=_kart_kimlik(lambda i: i in (10, 4), (10.0, 4.0, 1.0))),
}

# El değerlendirmesini değiştiren jokerler (etki hesabı değil, el tespiti bayrakları): puan_hesapla bunları otomatik bayrağa çevirir.
EL_BAYRAKLARI = {"j_four_fingers": "dort_parmak", "j_shortcut": "kisayol", "j_splash": "splash"}


def desteklenen_mi(joker: Joker) -> bool:
    """Jokerin etkisi bu dosyada (oyundan okunarak) tanımlı mı."""
    return joker.key in TANIMLAR or joker.key in EL_BAYRAKLARI


def bilinmeyenler(jokerler: list[Joker]) -> list[str]:
    """Verilen jokerlerden etkisi tanımlı olmayanların anahtarları."""
    return [j.key for j in jokerler if not desteklenen_mi(j)]


def uygula(chips: float, mult: float, etki: Etki) -> tuple[float, float]:
    """Bir etkiyi (chips, mult, çarpan) uygular: chips += c; mult = (mult + m) * çarpan."""
    c, m, x = etki
    return chips + c, (mult + m) * x


def kart_basina_uygula(
    chips: float, mult: float, kart: Kart, jokerler: list[Joker], baglam: Baglam
) -> tuple[float, float]:
    """Bir puanlayan kart için bütün jokerlerin kart başına etkilerini, joker sırasıyla uygular."""
    for j in jokerler:
        t = TANIMLAR.get(j.key)
        if t and t.kart_basina:
            chips, mult = uygula(chips, mult, t.kart_basina(kart, baglam))
    return chips, mult


def kart_vektoru(kart: Kart, jokerler: list[Joker], baglam: Baglam) -> tuple[float, float]:
    """Bir puanlayan kartın jokerlerden alacağı toplam (+chips, +mult) (çarpanlar yok sayılır); kart seçiminde sıralama ölçütüdür."""
    dc = dm = 0.0
    for j in jokerler:
        t = TANIMLAR.get(j.key)
        if t and t.kart_basina:
            c, m, _ = t.kart_basina(kart, baglam)
            dc += c
            dm += m
    return dc, dm


def ana_uygula(chips: float, mult: float, jokerler: list[Joker], baglam: Baglam) -> tuple[float, float]:
    """Ana joker aşaması: her joker için baskı (Foil, Holo), jokerin etkisi, en sonda Polychrome."""
    for j in jokerler:
        if j.baski == "foil":
            chips += 50
        elif j.baski == "holo":
            mult += 10
        t = TANIMLAR.get(j.key)
        if t and t.ana:
            chips, mult = uygula(chips, mult, t.ana(baglam))
        if j.baski == "polychrome":
            mult *= 1.5
    return chips, mult


def belirsiz_var_mi(jokerler: list[Joker]) -> bool:
    """Jokerlerden birinin etkisi rastgele (Misprint) mi."""
    return any(TANIMLAR[j.key].belirsiz for j in jokerler if j.key in TANIMLAR)


def apiden(kart: dict[str, Any]) -> Joker:
    """BalatroBot joker kartından Joker. Baskı `modifier.edition` içindedir; bilinmeyen baskı değeri hata verir."""
    mod = kart.get("modifier") or {}
    ham = mod.get("edition") if isinstance(mod, dict) else None
    if ham is None:
        return Joker(kart["key"])
    ad = {"FOIL": "foil", "HOLO": "holo", "HOLOGRAPHIC": "holo", "POLYCHROME": "polychrome", "NEGATIVE": "negative"}.get(
        str(ham).upper()
    )
    if ad is None:
        raise ValueError(f"Bilinmeyen joker baskısı: {ham!r}")
    return Joker(kart["key"], ad)
