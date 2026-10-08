"""BalatroBot (JSON-RPC 2.0 over HTTP) istemcisi.

Adil oyun kuralı: bot sadece bir insanın yapabileceği oyun aksiyonlarını kullanır.
BalatroBot'un `set`, `add`, `load`, `save`, `screenshot` uç noktaları (para/ante değiştirme,
kart ekleme, kayıt yükleme) bu istemcide bilerek yoktur.
"""

from __future__ import annotations

import itertools
import json
import urllib.error
import urllib.request
from typing import Any

VARSAYILAN_ADRES = "http://127.0.0.1:12346"

# Botun kullanabileceği oyun aksiyonları (insanın yapabildiği hamleler).
IZINLI_AKSIYONLAR = frozenset(
    {
        "start",
        "select",
        "skip",
        "play",
        "discard",
        "cash_out",
        "buy",
        "sell",
        "reroll",
        "next_round",
        "use",
        "rearrange",
        "menu",
    }
)
# Sadece okuma.
IZINLI_OKUMALAR = frozenset({"health", "gamestate"})


class BalatroHatasi(Exception):
    """İstemci tarafı tüm hataların tabanı."""


class BaglantiHatasi(BalatroHatasi):
    """Oyun kapalı, mod yüklenmemiş veya zaman aşımı."""


class ProtokolHatasi(BalatroHatasi):
    """Sunucudan beklenmeyen veya bozuk cevap geldi."""


class RpcHatasi(BalatroHatasi):
    def __init__(self, kod: int, mesaj: str, veri: Any = None):
        super().__init__(f"[{kod}] {mesaj}")
        self.kod = kod
        self.mesaj = mesaj
        self.veri = veri


class IcHata(RpcHatasi):  # -32000
    pass


class GecersizIstek(RpcHatasi):  # -32001
    pass


class GecersizDurum(RpcHatasi):  # -32002 (oyun şu an bu aksiyona uygun değil)
    pass


class IzinVerilmedi(RpcHatasi):  # -32003
    pass


_HATA_SINIFLARI = {
    -32000: IcHata,
    -32001: GecersizIstek,
    -32002: GecersizDurum,
    -32003: IzinVerilmedi,
}


class BalatroIstemci:
    def __init__(self, adres: str = VARSAYILAN_ADRES, zaman_asimi: float = 30.0):
        self.adres = adres
        self.zaman_asimi = zaman_asimi
        self._id = itertools.count(1)

    def _cagri(self, yontem: str, parametreler: dict[str, Any] | None = None) -> Any:
        if yontem not in IZINLI_AKSIYONLAR and yontem not in IZINLI_OKUMALAR:
            raise IzinVerilmedi(-32003, f"'{yontem}' bu istemcide izinli değil (adil oyun kuralı)")
        govde: dict[str, Any] = {"jsonrpc": "2.0", "method": yontem, "id": next(self._id)}
        if parametreler:
            govde["params"] = parametreler
        istek = urllib.request.Request(
            self.adres,
            data=json.dumps(govde).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(istek, timeout=self.zaman_asimi) as cevap:
                ham = cevap.read()
        except urllib.error.URLError as e:
            raise BaglantiHatasi(f"{self.adres} adresine bağlanılamadı: {e.reason}") from e
        except TimeoutError as e:
            raise BaglantiHatasi(f"{self.adres} zaman aşımı ({self.zaman_asimi} sn)") from e
        try:
            veri = json.loads(ham)
        except json.JSONDecodeError as e:
            raise ProtokolHatasi(f"Geçersiz JSON cevabı: {ham[:200]!r}") from e
        if not isinstance(veri, dict) or veri.get("jsonrpc") != "2.0":
            raise ProtokolHatasi(f"JSON-RPC 2.0 cevabı değil: {str(veri)[:200]}")
        if veri.get("id") != govde["id"]:
            raise ProtokolHatasi(f"Cevap kimliği uyuşmuyor: {veri.get('id')} != {govde['id']}")
        if "error" in veri:
            hata = veri["error"]
            sinif = _HATA_SINIFLARI.get(hata.get("code"), RpcHatasi)
            raise sinif(hata.get("code", 0), hata.get("message", ""), hata.get("data"))
        if "result" not in veri:
            raise ProtokolHatasi("Cevapta ne 'result' ne 'error' var")
        return veri["result"]

    # --- okuma ---
    def saglik(self) -> bool:
        return self._cagri("health").get("status") == "ok"

    def durum(self) -> dict[str, Any]:
        return self._cagri("gamestate")

    # --- aksiyonlar ---
    def baslat(self, deste: str, stake: str, seed: str | None = None) -> dict[str, Any]:
        p: dict[str, Any] = {"deck": deste, "stake": stake}
        if seed is not None:
            p["seed"] = seed
        return self._cagri("start", p)

    def blind_sec(self) -> dict[str, Any]:
        return self._cagri("select")

    def blind_atla(self) -> dict[str, Any]:
        return self._cagri("skip")

    def oyna(self, kartlar: list[int]) -> dict[str, Any]:
        return self._cagri("play", {"cards": kartlar})

    def at(self, kartlar: list[int]) -> dict[str, Any]:
        return self._cagri("discard", {"cards": kartlar})

    def odul_al(self) -> dict[str, Any]:
        return self._cagri("cash_out")

    def satin_al(self, **hedef: int) -> dict[str, Any]:
        """`card=`, `voucher=` veya `pack=` ile bir mağaza dizini."""
        return self._cagri("buy", hedef)

    def sat(self, **hedef: int) -> dict[str, Any]:
        """`joker=` veya `consumable=` ile dizin."""
        return self._cagri("sell", hedef)

    def yenile(self) -> dict[str, Any]:
        return self._cagri("reroll")

    def sonraki_tur(self) -> dict[str, Any]:
        return self._cagri("next_round")

    def kullan(self, tuketilebilir: int, kartlar: list[int] | None = None) -> dict[str, Any]:
        p: dict[str, Any] = {"consumable": tuketilebilir}
        if kartlar is not None:
            p["cards"] = kartlar
        return self._cagri("use", p)

    def sirala(self, **sira: list[int]) -> dict[str, Any]:
        """`hand=`, `jokers=` veya `consumables=` ile yeni sıra."""
        return self._cagri("rearrange", sira)

    def menuye_don(self) -> dict[str, Any]:
        return self._cagri("menu")
