"""Puan hesabı: oyunun `G.FUNCS.evaluate_play` (functions/state_events.lua) akışının karşılığı.

Sıra (oyunla aynı):
  1. El türünün taban chips ve mult değeri (gezegenlerle yükselmiş seviye dahil).
  2. Puanlayan kartlar soldan sağa. Her kart (kırmızı mühürle iki kez): kart chip'i (+ bonus, kalıcı),
     mult kartı +4 mult, glass x2, sonra baskı (foil +50 chips, holo +10 mult, polychrome x1.5).
  3. Elde kalan kartlar soldan sağa: steel x1.5 mult (kırmızı mühürle iki kez).
  4. Jokerler soldan sağa (sim/jokerler.py: yalnızca oyundan okunup tanımlanmış olanlar; bilinmeyen joker hata verir).
  Skor = floor(chips * mult).

Bu sürümde YOK: tanımsız jokerler, boss blind etkileri (el/kart debuff'ı `debuff` alanıyla verilebilir), Lucky kartın
rastgele etkisi (kart varsa `belirsiz` doğru döner, etkisi sayılmaz), Wheel/Hook gibi rastgele etkiler.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from balatro_ai.sim import boss as boss_kurallari
from balatro_ai.sim import jokerler as joker_modulu
from balatro_ai.sim.el_turu import Degerlendirme, degerlendir
from balatro_ai.sim.kartlar import Kart

# game.lua G.GAME.hands (oyundan alındı): tür -> (chips, mult, seviye başına chips, seviye başına mult)
EL_TABLOSU: dict[str, tuple[int, int, int, int]] = {
    "Flush Five": (160, 16, 50, 3),
    "Flush House": (140, 14, 40, 4),
    "Five of a Kind": (120, 12, 35, 3),
    "Straight Flush": (100, 8, 40, 4),
    "Four of a Kind": (60, 7, 30, 3),
    "Full House": (40, 4, 25, 2),
    "Flush": (35, 4, 15, 2),
    "Straight": (30, 4, 30, 3),
    "Three of a Kind": (30, 3, 20, 2),
    "Two Pair": (20, 2, 20, 1),
    "Pair": (10, 2, 15, 1),
    "High Card": (5, 1, 10, 1),
}


def seviyeden(el_turu: str, seviye: int = 1) -> tuple[int, int]:
    """Seviyedeki (chips, mult): taban + (seviye-1) * seviye artışı."""
    c, m, lc, lm = EL_TABLOSU[el_turu]
    return c + (seviye - 1) * lc, m + (seviye - 1) * lm


@dataclass(frozen=True)
class PuanSonucu:
    """Bir elin puan sonucu: el türü, puanlayan kartlar, chips, mult, skor, belirsizlik ve isteğe bağlı adım adım kayıt.
    """
    el_turu: str
    puanlayan: tuple[int, ...]
    chips: float
    mult: float
    skor: int
    belirsiz: bool = False  # rastgele etkili (Lucky) kart var: skor kesin değil
    adimlar: tuple[tuple[str, float, float], ...] = field(default=())  # (açıklama, chips, mult)


def puan_hesapla(
    oynanan: list[Kart],
    elde: list[Kart] | tuple[Kart, ...] = (),
    *,
    el_degerleri: dict[str, tuple[float, float]] | None = None,
    seviyeler: dict[str, int] | None = None,
    jokerler: Sequence[joker_modulu.Joker] = (),
    baglam: joker_modulu.Baglam | None = None,
    el_debuff: bool = False,
    boss: str | None = None,
    gecmis_turler: frozenset[str] = frozenset(),
    ilk_tur: str | None = None,
    dort_parmak: bool = False,
    kisayol: bool = False,
    splash: bool = False,
    adim_kaydi: bool = False,
) -> PuanSonucu:
    """Oynanan kartların skorunu hesaplar.

    `el_degerleri`: oyun durumundaki güncel (chips, mult) (`state.hands[tür]`); verilmezse `seviyeler`
    (tür -> seviye) kullanılır, o da yoksa seviye 1.
    """
    jokerler = list(jokerler)
    bilinmeyen = joker_modulu.bilinmeyenler(jokerler)
    if bilinmeyen:  # etkisi oyundan okunup doğrulanmamış joker: sessizce yanlış hesaplamak yerine dur
        raise NotImplementedError(f"Etkisi tanımlı olmayan joker: {bilinmeyen}")
    for j in jokerler:  # el tespitini değiştiren jokerler (Four Fingers, Shortcut, Splash)
        bayrak = joker_modulu.EL_BAYRAKLARI.get(j.key)
        if bayrak == "dort_parmak":
            dort_parmak = True
        elif bayrak == "kisayol":
            kisayol = True
        elif bayrak == "splash":
            splash = True
    # Boss kart debuff'ları el tespitinden ÖNCE işaretlenir (oyunda da kartlar set_debuff ile işaretlidir);
    # el türü tespiti debuff'tan bağımsızdır, yalnızca puanlama debuff'lı kartı atlar.
    oynanan = boss_kurallari.kartlara_uygula(boss, list(oynanan))
    elde = boss_kurallari.kartlara_uygula(boss, list(elde))
    d: Degerlendirme = degerlendir(oynanan, dort_parmak=dort_parmak, kisayol=kisayol, splash=splash)
    if el_degerleri and d.el_turu in el_degerleri:
        chips, mult = (float(x) for x in el_degerleri[d.el_turu])
    else:
        chips, mult = (float(x) for x in seviyeden(d.el_turu, (seviyeler or {}).get(d.el_turu, 1)))
    if boss == "The Arm":  # puanlamadan önce oynanan türün seviyesi 1 düşer (seviye > 1 ise)
        c0, _, lc, lm = EL_TABLOSU[d.el_turu]
        if lc and chips > c0 + 0.5 * lc:
            chips, mult = chips - lc, max(mult - lm, 1.0)
    jb = replace(
        baglam or joker_modulu.Baglam(),
        el_turu=d.el_turu, iceren=frozenset(d.iceren), oynanan_sayisi=len(oynanan), joker_sayisi=len(jokerler),
    )
    adimlar: list[tuple[str, float, float]] = []

    def kayit(ad: str) -> None:
        """Adım kaydı açıksa şimdiki chips ve mult değerini açıklamayla listeye ekler."""
        if adim_kaydi:
            adimlar.append((ad, chips, mult))

    kayit(f"taban {d.el_turu}")
    if el_debuff or boss_kurallari.el_debuff_mi(boss, len(oynanan), d.el_turu, gecmis_turler, ilk_tur):  # boss el türünü engelledi: skor 0
        return PuanSonucu(d.el_turu, d.puanlayan, chips, mult, 0, adimlar=tuple(adimlar))
    chips, mult = boss_kurallari.taban_degistir(boss, chips, mult)
    if boss:
        kayit("boss taban")

    belirsiz = False
    for i in d.puanlayan:  # soldan sağa (oynama sırası)
        k = oynanan[i]
        if k.debuff:
            kayit(f"kart {i} debuff")
            continue
        tekrar = 2 if k.muhur == "red" else 1
        for _ in range(tekrar):
            chips += k.chip
            if k.gelistirme == "mult":
                mult += 4
            elif k.gelistirme == "lucky":
                belirsiz = True
            if k.gelistirme == "glass":
                mult *= 2
            if k.baski == "foil":
                chips += 50
            elif k.baski == "holo":
                mult += 10
            elif k.baski == "polychrome":
                mult *= 1.5
            chips, mult = joker_modulu.kart_basina_uygula(chips, mult, k, jokerler, jb)  # jokerlerin kart başına etkisi
            kayit(f"kart {i} ({k.rutbe}{k.renk})")
    for i, k in enumerate(elde):  # elde kalan kartlar
        if k.debuff or k.gelistirme != "steel":
            continue
        for _ in range(2 if k.muhur == "red" else 1):
            mult *= 1.5
            kayit(f"elde {i} steel")
    chips, mult = joker_modulu.ana_uygula(chips, mult, jokerler, jb)  # jokerlerin ana aşaması (baskı, etki, polychrome)
    kayit("jokerler")
    belirsiz = belirsiz or joker_modulu.belirsiz_var_mi(jokerler)
    return PuanSonucu(
        el_turu=d.el_turu,
        puanlayan=d.puanlayan,
        chips=chips,
        mult=mult,
        skor=math.floor(chips * mult),
        belirsiz=belirsiz,
        adimlar=tuple(adimlar),
    )
