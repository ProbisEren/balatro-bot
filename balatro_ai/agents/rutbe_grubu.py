"""Basit test ajanı: eldeki en büyük aynı rütbeli grupları oynar; diğer kararları rastgele verir.

Öğrenen ya da puan hesaplayan bir ajan DEĞİL (flush, seri ve joker etkilerini bilmez). Rastgele
ajandan daha uzun yaşayıp mağaza ve paket aşamalarına ulaştığı için ortamı ve logu bu aşamalarda
sınamak için kullanılır.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from balatro_ai.env import aksiyonlar

SIRA = {r: i for i, r in enumerate("23456789TJQKA")}


def _secilecek_kartlar(kartlar: list[dict[str, Any]]) -> list[int]:
    """Eldeki en büyük aynı rütbeli grupları (çift, üçlü, iki çift...) seçer; yoksa en yüksek tek kartı. Oynanacak kart indekslerini döndürür.
    """
    n = min(len(kartlar), aksiyonlar.MAKS_EL)
    gruplar: dict[str, list[int]] = defaultdict(list)
    for i in range(n):
        gruplar[kartlar[i]["value"]["rank"]].append(i)
    sirali = sorted(gruplar.values(), key=lambda g: (len(g), SIRA.get(kartlar[g[0]]["value"]["rank"], -1)), reverse=True)
    secim: list[int] = []
    for g in sirali:
        if len(g) >= 2 and len(secim) + len(g) <= aksiyonlar.MAKS_KART:
            secim += g
    if not secim:  # çift yok: en yüksek kart
        secim = [max(range(n), key=lambda i: SIRA.get(kartlar[i]["value"]["rank"], -1))]
    return sorted(secim)


class RutbeGrubuAjan:
    """Test ajanı: elde en büyük aynı rütbeli grubu oynar, diğer aşamalarda rastgele seçer. Öğrenmez, ortamı sınamak içindir.
    """
    tur = "rutbe_grubu"

    def __init__(self, tohum: int):
        """Ajanı verilen tohumla başlatır."""
        self.tohum = tohum
        self._rng = random.Random(tohum)

    def bilgi(self) -> dict[str, Any]:
        """Run kaydındaki `ajan` alanına yazılacak kimlik bilgisini döndürür."""
        return {"tur": self.tur, "model_id": None, "rng_tohumu": self.tohum}

    def sec(self, gozlem: dict[str, Any], bilgi: dict[str, Any]) -> int:
        """El seçiminde en büyük rütbe grubunu oynar; diğer aşamalarda geçerli aksiyonlardan rastgele seçer.
        """
        gecerli = bilgi["gecerli_aksiyonlar"]
        if gozlem.get("state") == "SELECTING_HAND" and gozlem["hand"]["cards"]:
            hedef = aksiyonlar.KOMBINASYONLAR.index(tuple(_secilecek_kartlar(gozlem["hand"]["cards"])))
            if hedef in gecerli:
                return hedef
        return self._rng.choice(gecerli)
