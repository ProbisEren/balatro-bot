"""Ham oyun durumunu "bir insanın görebildiği" gözleme çevirir.

BalatroBot `gamestate` cevabı iki yerde gizli bilgi sızdırır (2026-10-08'de gerçek oyunda doğrulandı):
- `seed`: oyunun tohumu, gelecek her şeyi belirler.
- `cards` (deste): round içinde kalan deste çekiliş sırasında listelenir; sonraki çekilişler
  listenin sonundan ters sırayla gelir.
- Yüzü kapalı kartlar (`state.hidden`): bazı boss'lar eldeki kartı kapatır, API yine de
  kartın rank/suit bilgisini verir. İnsan bunu göremez.
Bot bu bilgileri hiçbir koşulda görmemelidir (docs/PLAN.md, adil oyun kuralı).
"""

from __future__ import annotations

import copy
from typing import Any

# Bir insanın görmediği üst düzey alanlar.
GIZLI_ALANLAR = frozenset({"seed"})

# Kapalı kartın kimliğinin maskelendiği alanlar. Deste (`cards`) burada yok: oyunda deste
# ekranı kalan kartları gösterir, tüm deste kartları teknik olarak "kapalı" işaretlidir.
KART_ALANLARI = ("hand", "jokers", "consumables", "shop", "vouchers", "packs", "pack")


def _kapali_mi(kart: dict[str, Any]) -> bool:
    """Kartın yüzü kapalı mı (`state.hidden`)."""
    durum = kart.get("state")
    return isinstance(durum, dict) and bool(durum.get("hidden"))


def _kapali_karti_maskele(alan: dict[str, Any]) -> None:
    """Bir kart alanındaki yüzü kapalı kartların kimliğini siler, yalnızca 'kapalı' bilgisini bırakır.
    """
    kartlar = alan.get("cards")
    if not isinstance(kartlar, list):
        return
    for i, kart in enumerate(kartlar):
        if isinstance(kart, dict) and _kapali_mi(kart):
            kartlar[i] = {"state": {"hidden": True}}


def insan_gozlemi(durum: dict[str, Any]) -> dict[str, Any]:
    """`durum`u değiştirmeden, gizli bilgiden arındırılmış bir kopya döndürür.

    Deste kartları sıradan bağımsız, kart anahtarına göre sıralı verilir; böylece listenin
    sırası çekiliş sırası hakkında hiçbir şey söylemez. İnsan da destede hangi kartların
    kaldığını (kart sayarak) bilebilir, sırasını bilemez.
    """
    gozlem = copy.deepcopy(durum)
    for alan in GIZLI_ALANLAR:
        gozlem.pop(alan, None)
    for ad in KART_ALANLARI:
        alan = gozlem.get(ad)
        if isinstance(alan, dict):
            _kapali_karti_maskele(alan)
    deste = gozlem.get("cards")
    if isinstance(deste, dict) and isinstance(deste.get("cards"), list):
        deste["cards"] = sorted(deste["cards"], key=lambda k: (k.get("key", ""), k.get("id", 0)))
    return gozlem
