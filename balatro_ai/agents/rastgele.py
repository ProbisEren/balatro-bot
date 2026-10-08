"""Rastgele ajan: geçerli aksiyonlar arasından düzgün dağılımla seçer.

Alt sınırdır ve veri hattının ilk testidir (docs/PLAN.md, Bölüm 7, basamak 1). Yalnızca ortamın
verdiği geçerli aksiyon kimliklerini görür; oyun durumunu hiç kullanmaz.
"""

from __future__ import annotations

import random
from typing import Any


class RastgeleAjan:
    """Geçerli aksiyonlar arasından rastgele seçen ajan; her ajanın geçmesi gereken alt sınırdır."""
    tur = "random"

    def __init__(self, tohum: int):
        """Ajanı verilen tohumla başlatır (aynı tohum aynı seçimleri verir)."""
        self.tohum = tohum
        self._rng = random.Random(tohum)

    def bilgi(self) -> dict[str, Any]:
        """Run kaydına (`ajan`) yazılacak kimlik bilgisi."""
        return {"tur": self.tur, "model_id": None, "rng_tohumu": self.tohum}

    def sec(self, gozlem: dict[str, Any], bilgi: dict[str, Any]) -> int:
        """Ortamın verdiği geçerli aksiyonlardan birini düzgün dağılımla seçer; oyun durumuna bakmaz.
        """
        return self._rng.choice(bilgi["gecerli_aksiyonlar"])
