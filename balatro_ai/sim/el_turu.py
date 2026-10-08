"""Poker eli tespiti: oyunun `evaluate_poker_hand` (functions/misc_functions.lua) fonksiyonunun karşılığı.

Kurallar oyundan alınmıştır:
- `grup_sayisi` (get_X_same): tam olarak N kartlı rütbe grupları, rütbesi büyükten küçüğe.
- Flush: tam 5 kart (Four Fingers ile 4), aynı renk; Wild her rengi sayar.
- Straight: A düşük (A-2-3-4-5) ve yüksek (10-J-Q-K-A) olabilir, köşe sarma yok; Shortcut bir rütbe atlatır.
- Puanlayan kartlar: `evaluate_play` içinde seçilen elin kartları + Stone kartlar (+ Splash ile hepsi).
"""

from __future__ import annotations

from dataclasses import dataclass

from balatro_ai.sim.kartlar import RENKLER, Kart

EL_TURLERI = (
    "Flush Five", "Flush House", "Five of a Kind", "Straight Flush", "Four of a Kind", "Full House",
    "Flush", "Straight", "Three of a Kind", "Two Pair", "Pair", "High Card",
)  # oyundaki öncelik sırası (en güçlü önce)


@dataclass(frozen=True)
class Degerlendirme:
    """Bir elin tespit sonucu: el türü, puanlayan kart indeksleri ve elin içerdiği türler."""
    el_turu: str
    puanlayan: tuple[int, ...]  # oynanan kartlar içindeki indeksler (oynama sırasında)
    iceren: frozenset[str]  # elin içerdiği türler (jokerlerin "contains" koşulları için)


def grup_sayisi(kartlar: list[tuple[int, Kart]], n: int) -> list[list[int]]:
    """Tam n kartlı rütbe grupları (oyun içi indeksler), rütbe kimliği büyükten küçüğe."""
    gruplar: dict[int, list[int]] = {}
    for i, k in kartlar:
        if k.rutbe_id is not None:
            gruplar.setdefault(k.rutbe_id, []).append(i)
    return [gruplar[r] for r in sorted(gruplar, reverse=True) if len(gruplar[r]) == n]


def _flush(kartlar: list[tuple[int, Kart]], dort_parmak: bool) -> list[int]:
    """Flush'ı oluşturan kart indekslerini döndürür (yoksa boş liste)."""
    gerekli = 4 if dort_parmak else 5
    if len(kartlar) > 5 or len(kartlar) < gerekli:
        return []
    for renk in RENKLER:
        uyan = [i for i, k in kartlar if k.renk_uyar(renk)]
        if len(uyan) >= gerekli:
            return uyan
    return []


def _straight(kartlar: list[tuple[int, Kart]], dort_parmak: bool, kisayol: bool) -> list[int]:
    """Straight'i oluşturan kart indekslerini döndürür; As düşük/yüksek, Shortcut ve Four Fingers dahil (yoksa boş).
    """
    gerekli = 4 if dort_parmak else 5
    if len(kartlar) > 5 or len(kartlar) < gerekli:
        return []
    kimlikler: dict[int, list[int]] = {}
    for i, k in kartlar:
        if k.rutbe_id is not None and 1 < k.rutbe_id < 15:
            kimlikler.setdefault(k.rutbe_id, []).append(i)
    t: list[int] = []
    uzunluk = 0
    seri = False
    atlandi = False
    for j in range(1, 15):
        kimlik = 14 if j == 1 else j
        if kimlik in kimlikler:
            uzunluk += 1
            atlandi = False
            t += kimlikler[kimlik]
        elif kisayol and not atlandi and j != 14:
            atlandi = True
        else:
            uzunluk = 0
            atlandi = False
            if not seri:
                t = []
            if seri:
                break
        if uzunluk >= gerekli:
            seri = True
    return t if seri else []


def _en_yuksek(kartlar: list[tuple[int, Kart]]) -> list[int]:
    """High Card için en yüksek kartın indeksini döndürür (Stone kartlar seçilmez)."""
    if not kartlar:
        return []
    return [max(kartlar, key=lambda ik: ik[1].en_yuksek_anahtari)[0]]


def degerlendir(
    kartlar: list[Kart], *, dort_parmak: bool = False, kisayol: bool = False, splash: bool = False
) -> Degerlendirme:
    """Oynanan kartların el türünü ve puanlayan kartlarını belirler."""
    if not 1 <= len(kartlar) <= 5:
        raise ValueError(f"1-5 kart oynanır, verilen: {len(kartlar)}")
    ik = list(enumerate(kartlar))
    p5, p4, p3, p2 = (grup_sayisi(ik, n) for n in (5, 4, 3, 2))
    fl = _flush(ik, dort_parmak)
    st = _straight(ik, dort_parmak, kisayol)

    sonuc: dict[str, list[list[int]]] = {t: [] for t in EL_TURLERI}
    if p5 and fl:
        sonuc["Flush Five"] = p5
    if p3 and p2 and fl:
        sonuc["Flush House"] = [p3[0] + p2[0]]
    if p5:
        sonuc["Five of a Kind"] = p5
    if fl and st:
        sonuc["Straight Flush"] = [fl + [i for i in st if i not in fl]]
    if p4:
        sonuc["Four of a Kind"] = p4
    if p3 and p2:
        sonuc["Full House"] = [p3[0] + p2[0]]
    if fl:
        sonuc["Flush"] = [fl]
    if st:
        sonuc["Straight"] = [st]
    if p3:
        sonuc["Three of a Kind"] = p3
    if len(p2) == 2 or (len(p3) == 1 and len(p2) == 1):
        ikinci = p2[1] if len(p2) > 1 else p3[0]
        sonuc["Two Pair"] = [p2[0] + ikinci]
    if p2:
        sonuc["Pair"] = p2
    en = _en_yuksek(ik)
    if en:
        sonuc["High Card"] = [en]
    # Üstteki türün alt türleri de "içerilir" (oyunun sonundaki türetme).
    if sonuc["Five of a Kind"]:
        sonuc["Four of a Kind"] = [sonuc["Five of a Kind"][0][:4]]
    if sonuc["Four of a Kind"]:
        sonuc["Three of a Kind"] = [sonuc["Four of a Kind"][0][:3]]
    if sonuc["Three of a Kind"]:
        sonuc["Pair"] = [sonuc["Three of a Kind"][0][:2]]

    tur = next(t for t in EL_TURLERI if sonuc[t])
    puanlayan = list(sonuc[tur][0])
    if splash:
        puanlayan = list(range(len(kartlar)))
    else:  # saf bonus kartlar (Stone) her zaman puanlar
        puanlayan += [i for i, k in ik if k.tas_mi and i not in puanlayan]
    return Degerlendirme(
        el_turu=tur,
        puanlayan=tuple(sorted(set(puanlayan))),
        iceren=frozenset(t for t in EL_TURLERI if sonuc[t]),
    )
