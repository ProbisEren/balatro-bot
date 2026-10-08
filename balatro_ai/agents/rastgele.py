"""Rastgele ajan: geçerli aksiyonlar arasından düzgün dağılımla seçer.

Alt sınırdır ve veri hattının ilk testidir (docs/PLAN.md, Bölüm 7, basamak 1). Yalnızca ortamın
verdiği geçerli aksiyon kimliklerini görür; oyun durumunu hiç kullanmaz.
"""

from __future__ import annotations

import random
from typing import Any


class RastgeleAjan:
    tur = "random"

    def __init__(self, tohum: int):
        self.tohum = tohum
        self._rng = random.Random(tohum)

    def bilgi(self) -> dict[str, Any]:
        """Run kaydına (`ajan`) yazılacak kimlik bilgisi."""
        return {"tur": self.tur, "model_id": None, "rng_tohumu": self.tohum}

    def sec(self, gozlem: dict[str, Any], bilgi: dict[str, Any]) -> int:
        return self._rng.choice(bilgi["gecerli_aksiyonlar"])
