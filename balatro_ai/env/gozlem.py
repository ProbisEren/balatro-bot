"""Ham oyun durumunu "bir insanın görebildiği" gözleme çevirir.

BalatroBot `gamestate` cevabı iki yerde gizli bilgi sızdırır (2026-10-08'de gerçek oyunda doğrulandı):
- `seed`: oyunun tohumu, gelecek her şeyi belirler.
- `cards` (deste): round içinde kalan deste çekiliş sırasında listelenir; sonraki çekilişler
  listenin sonundan ters sırayla gelir.
Bot bu iki bilgiyi hiçbir koşulda görmemelidir (docs/PLAN.md, adil oyun kuralı).
"""

from __future__ import annotations

import copy
from typing import Any

# Bir insanın görmediği üst düzey alanlar.
GIZLI_ALANLAR = frozenset({"seed"})


def insan_gozlemi(durum: dict[str, Any]) -> dict[str, Any]:
    """`durum`u değiştirmeden, gizli bilgiden arındırılmış bir kopya döndürür.

    Deste kartları sıradan bağımsız, kart anahtarına göre sıralı verilir; böylece listenin
    sırası çekiliş sırası hakkında hiçbir şey söylemez. İnsan da destede hangi kartların
    kaldığını (kart sayarak) bilebilir, sırasını bilemez.
    """
    gozlem = copy.deepcopy(durum)
    for alan in GIZLI_ALANLAR:
        gozlem.pop(alan, None)
    deste = gozlem.get("cards")
    if isinstance(deste, dict) and isinstance(deste.get("cards"), list):
        deste["cards"] = sorted(deste["cards"], key=lambda k: (k.get("key", ""), k.get("id", 0)))
    return gozlem
