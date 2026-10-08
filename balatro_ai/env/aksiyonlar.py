"""Aksiyon uzayı: botun seçebildiği hamleleri numaralandırır ve o anda geçerli olanları bulur.

İki aksiyon kümesi, aynı ortam ve aynı logger üzerinde karşılaştırılabilsin diye:
  "dar": yalnızca el oynama ve discard. Blind seçimi, mağaza, paket gibi aşamalar sabit
         kurallarla otomatik geçilir (ortam.py).
  "tam": el oynama/discard + blind seç/atla, mağaza (al, sat, yenile, çık), paket (seç, atla),
         hedefsiz tüketilebilir kullanımı.

Aksiyon kimlikleri sabittir (durumdan bağımsız); geçerlilik `gecerli(durum)` ile hesaplanır.
Girdi olarak insan gözlemi DEĞİL, ham durum alınır: geçerli aksiyonları yalnızca ortam
hesaplar, bota yalnızca aksiyon kimlikleri gider.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

MAKS_EL = 10  # Aksiyon uzayının desteklediği en büyük el boyutu (Juggler vb. ile 8'in üstü olabilir).
MAKS_KART = 5  # Bir seferde oynanabilen/atılabilen en çok kart.
KUMELER = ("dar", "tam")

# Mağaza ve diğer alanların kimlik aralıkları (tam küme).
MAKS_MAGAZA_KART = 6
MAKS_KUPON = 3
MAKS_MAGAZA_PAKET = 4
MAKS_JOKER = 10
MAKS_TUKETILEBILIR = 4
MAKS_PAKET_KART = 6

# Bütün olası kart seçimleri (indeks demetleri): boyuta göre sıralı, her boyutta sözlük sırası.
KOMBINASYONLAR: tuple[tuple[int, ...], ...] = tuple(
    c for k in range(1, MAKS_KART + 1) for c in combinations(range(MAKS_EL), k)
)
K = len(KOMBINASYONLAR)  # 637

# Hedef kart seçimi (tarot/spektral): eldeki 1-3 kart, 175 kombinasyon.
MAKS_HEDEF = 3
HEDEF_KOMBI: tuple[tuple[int, ...], ...] = tuple(
    c for k in range(1, MAKS_HEDEF + 1) for c in combinations(range(MAKS_EL), k)
)
H = len(HEDEF_KOMBI)

# Kimlik düzeni.
_OYNA = 0
_AT = K
_BLIND_SEC = 2 * K
_BLIND_ATLA = _BLIND_SEC + 1
_AL_KART = _BLIND_ATLA + 1
_AL_KUPON = _AL_KART + MAKS_MAGAZA_KART
_AL_PAKET = _AL_KUPON + MAKS_KUPON
_SAT_JOKER = _AL_PAKET + MAKS_MAGAZA_PAKET
_SAT_TUK = _SAT_JOKER + MAKS_JOKER
_YENILE = _SAT_TUK + MAKS_TUKETILEBILIR
_MAGAZADAN_CIK = _YENILE + 1
_PAKET_SEC = _MAGAZADAN_CIK + 1
_PAKET_ATLA = _PAKET_SEC + MAKS_PAKET_KART
_KULLAN = _PAKET_ATLA + 1
_PAKET_HEDEFLI = _KULLAN + MAKS_TUKETILEBILIR
_KULLAN_HEDEFLI = _PAKET_HEDEFLI + MAKS_PAKET_KART * H
TOPLAM_TAM = _KULLAN_HEDEFLI + MAKS_TUKETILEBILIR * H
TOPLAM_DAR = 2 * K


def aksiyon_sayisi(kume: str) -> int:
    return TOPLAM_DAR if kume == "dar" else TOPLAM_TAM


def _sayi(durum: dict[str, Any], alan: str) -> int:
    a = durum.get(alan)
    return len(a["cards"]) if isinstance(a, dict) and isinstance(a.get("cards"), list) else 0


def _kartlar(durum: dict[str, Any], alan: str) -> list[dict[str, Any]]:
    a = durum.get(alan)
    return a["cards"] if isinstance(a, dict) and isinstance(a.get("cards"), list) else []


def komut(aksiyon_id: int, durum: dict[str, Any] | None = None) -> dict[str, Any]:
    """Kimliği oyun komutuna çevirir: {"yontem": ..., "parametreler": ...}."""
    a = aksiyon_id
    if 0 <= a < K:
        return {"yontem": "play", "parametreler": {"cards": list(KOMBINASYONLAR[a])}}
    if K <= a < 2 * K:
        return {"yontem": "discard", "parametreler": {"cards": list(KOMBINASYONLAR[a - K])}}
    if a == _BLIND_SEC:
        return {"yontem": "select", "parametreler": None}
    if a == _BLIND_ATLA:
        return {"yontem": "skip", "parametreler": None}
    if _AL_KART <= a < _AL_KUPON:
        return {"yontem": "buy", "parametreler": {"card": a - _AL_KART}}
    if _AL_KUPON <= a < _AL_PAKET:
        return {"yontem": "buy", "parametreler": {"voucher": a - _AL_KUPON}}
    if _AL_PAKET <= a < _SAT_JOKER:
        return {"yontem": "buy", "parametreler": {"pack": a - _AL_PAKET}}
    if _SAT_JOKER <= a < _SAT_TUK:
        return {"yontem": "sell", "parametreler": {"joker": a - _SAT_JOKER}}
    if _SAT_TUK <= a < _YENILE:
        return {"yontem": "sell", "parametreler": {"consumable": a - _SAT_TUK}}
    if a == _YENILE:
        return {"yontem": "reroll", "parametreler": None}
    if a == _MAGAZADAN_CIK:
        return {"yontem": "next_round", "parametreler": None}
    if _PAKET_SEC <= a < _PAKET_ATLA:
        return {"yontem": "pack", "parametreler": {"card": a - _PAKET_SEC}}
    if a == _PAKET_ATLA:
        return {"yontem": "pack", "parametreler": {"skip": True}}
    if _KULLAN <= a < _PAKET_HEDEFLI:
        return {"yontem": "use", "parametreler": {"consumable": a - _KULLAN}}
    if _PAKET_HEDEFLI <= a < _KULLAN_HEDEFLI:
        kart, kombi = divmod(a - _PAKET_HEDEFLI, H)
        return {"yontem": "pack", "parametreler": {"card": kart, "targets": list(HEDEF_KOMBI[kombi])}}
    if _KULLAN_HEDEFLI <= a < TOPLAM_TAM:
        tuk, kombi = divmod(a - _KULLAN_HEDEFLI, H)
        return {"yontem": "use", "parametreler": {"consumable": tuk, "cards": list(HEDEF_KOMBI[kombi])}}
    raise ValueError(f"Bilinmeyen aksiyon kimliği: {aksiyon_id}")


def _el_aksiyonlari(durum: dict[str, Any]) -> list[int]:
    n = min(_sayi(durum, "hand"), MAKS_EL)
    rnd = durum.get("round") or {}
    sinir = [i for i, c in enumerate(KOMBINASYONLAR) if c[-1] < n]
    ids = []
    if rnd.get("hands_left", 0) > 0:
        ids += [_OYNA + i for i in sinir]
    if rnd.get("discards_left", 0) > 0:
        ids += [_AT + i for i in sinir]
    return ids


Gereksinim = dict[str, tuple[int, int]]  # kart anahtarı -> (en az, en çok) hedef kart sayısı


def _hedefli_secimler(
    kart_anahtari: str | None, el_boyu: int, gereksinim: Gereksinim, hedefsiz_id: int, hedefli_taban: int
) -> list[int]:
    """Bir paket/tüketilebilir kart için seçenekler: hedef sayısı biliniyorsa yalnızca geçerli
    hedef kombinasyonları, bilinmiyorsa hedefsiz seçim (oyun reddederse sayı öğrenilir)."""
    bilinen = gereksinim.get(kart_anahtari) if kart_anahtari else None
    if not bilinen or bilinen[1] == 0:
        return [hedefsiz_id]
    mn, mx = bilinen
    return [
        hedefli_taban + i
        for i, c in enumerate(HEDEF_KOMBI)
        if mn <= len(c) <= mx and c[-1] < min(el_boyu, MAKS_EL)
    ]


def _tuketilebilir_secimi(durum: dict[str, Any], gereksinim: Gereksinim) -> list[int]:
    ids: list[int] = []
    el = _sayi(durum, "hand")
    for i, k in enumerate(_kartlar(durum, "consumables")[:MAKS_TUKETILEBILIR]):
        ids += _hedefli_secimler(k.get("key"), el, gereksinim, _KULLAN + i, _KULLAN_HEDEFLI + i * H)
    return ids


def gecerli(
    durum: dict[str, Any],
    kume: str,
    engelli: frozenset[int] = frozenset(),
    gereksinim: Gereksinim | None = None,
) -> list[int]:
    """O anki durumda geçerli aksiyon kimlikleri. `engelli`: bu durumda oyunun reddettiği kimlikler."""
    gereksinim = gereksinim or {}
    faz = durum.get("state")
    ids: list[int] = []
    para = durum.get("money", 0)
    if faz == "SELECTING_HAND":
        ids = _el_aksiyonlari(durum)
        if kume == "tam":
            ids += _tuketilebilir_secimi(durum, gereksinim)
    elif kume == "tam" and faz == "BLIND_SELECT":
        ids = [_BLIND_SEC]
        siradaki = next(
            (b for b in (durum.get("blinds") or {}).values() if b.get("status") == "SELECT"), None
        )
        if siradaki is not None and siradaki.get("type") != "BOSS":
            ids.append(_BLIND_ATLA)
    elif kume == "tam" and faz == "SHOP":
        joker_yer = _sayi(durum, "jokers") < (durum.get("jokers") or {}).get("limit", 5)
        tuk_yer = _sayi(durum, "consumables") < (durum.get("consumables") or {}).get("limit", 2)
        for i, k in enumerate(_kartlar(durum, "shop")[:MAKS_MAGAZA_KART]):
            yer = joker_yer if k.get("set") == "JOKER" else tuk_yer
            if k["cost"]["buy"] <= para and yer:
                ids.append(_AL_KART + i)
        for i, k in enumerate(_kartlar(durum, "vouchers")[:MAKS_KUPON]):
            if k["cost"]["buy"] <= para:
                ids.append(_AL_KUPON + i)
        for i, k in enumerate(_kartlar(durum, "packs")[:MAKS_MAGAZA_PAKET]):
            if k["cost"]["buy"] <= para:
                ids.append(_AL_PAKET + i)
        ids += [_SAT_JOKER + i for i in range(min(_sayi(durum, "jokers"), MAKS_JOKER))]
        ids += [_SAT_TUK + i for i in range(min(_sayi(durum, "consumables"), MAKS_TUKETILEBILIR))]
        if para >= (durum.get("round") or {}).get("reroll_cost", 5):
            ids.append(_YENILE)
        ids.append(_MAGAZADAN_CIK)
        ids += _tuketilebilir_secimi(durum, gereksinim)
    elif kume == "tam" and faz in PAKET_FAZLARI:
        el = _sayi(durum, "hand")
        for i, k in enumerate(_kartlar(durum, "pack")[:MAKS_PAKET_KART]):
            ids += _hedefli_secimler(k.get("key"), el, gereksinim, _PAKET_SEC + i, _PAKET_HEDEFLI + i * H)
        ids.append(_PAKET_ATLA)
    return [i for i in ids if i not in engelli]


PAKET_FAZLARI = frozenset(
    {"SMODS_BOOSTER_OPENED", "TAROT_PACK", "PLANET_PACK", "SPECTRAL_PACK", "STANDARD_PACK", "BUFFOON_PACK"}
)
