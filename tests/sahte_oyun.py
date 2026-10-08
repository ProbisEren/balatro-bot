"""Gerçek oyun yokken ortamı sınamak için küçük, deterministik sahte Balatro.

Gerçek oyunun kuralları değildir: yalnızca ortamın okuduğu durum alanlarını ve faz geçişlerini
(BLIND_SELECT → SELECTING_HAND → ROUND_EVAL → SHOP → ...) taklit eder.
"""

from __future__ import annotations

import copy
import random
import time
from typing import Any

from balatro_ai.env.client import BaglantiHatasi, GecersizDurum, GecersizIstek

SUITS, RANKS = "HDCS", "23456789TJQKA"
HEDEF = {"SMALL": 100, "BIG": 150, "BOSS": 200}
KAZANMA_ANTE = 2


def _kart(i: int, key: str) -> dict[str, Any]:
    """Verilen anahtardan, gerçek oyundaki kart sözlüğü biçiminde bir oyun kartı üretir."""
    return {"id": 800 + i, "key": key, "label": "Base Card", "set": "DEFAULT",
            "cost": {"buy": 1, "sell": 1}, "modifier": [], "state": [],
            "value": {"rank": key[2], "suit": key[0], "effect": "x"}}


def _teklif(key: str, set_: str, fiyat: int) -> dict[str, Any]:
    """Mağaza teklifi (joker, gezegen, kupon, paket) sözlüğü üretir."""
    return {"key": key, "label": key, "set": set_, "cost": {"buy": fiyat, "sell": 1},
            "modifier": [], "state": [], "value": {"effect": "e"}}


class SahteOyun:
    """Gerçek oyun yokken ortamı sınamak için küçük sahte Balatro; BalatroBot istemcisiyle aynı arayüzü (`durum`, `komut`, `saglik`) sunar.
    """
    def __init__(self):
        """Sahte oyunu ana menüde başlatır ve test ayarlarını (zorla reddet, gecikmeli paket, cevapsız pack) kurar.
        """
        self.state = "MENU"
        self.zorla_red: set[str] = set()
        self.skip_sonrasi_gecikmeli_paket = False
        self.pack_cevapsiz = False
        self.hedef_gerekir: dict[str, tuple[int, int]] = {}
        self._paket_zamani: float | None = None
        self.cagrilar: list[tuple[str, Any]] = []
        self._sifirla()

    def _sifirla(self):
        """Run durumunu (ante, para, deste, el, blind, mağaza) başlangıç değerlerine döndürür."""
        self.ante = 1
        self.round_no = 0
        self.money = 4
        self.won = False
        self.seed = None
        self.deste: list[dict] = []
        self.el: list[dict] = []
        self.jokers: list[dict] = []
        self.tuk: list[dict] = []
        self.hands_left = self.discards_left = self.chips = 0
        self.blinds = self._yeni_blindler()
        self.magaza: dict[str, list] = {"shop": [], "vouchers": [], "packs": []}
        self.paket: list[dict] = []
        self.reroll = 5

    def _yeni_blindler(self):
        """Yeni bir ante için Small, Big ve Boss blind'ları ve hedef skorlarını üretir."""
        return {
            "small": {"type": "SMALL", "name": "Small Blind", "score": HEDEF["SMALL"], "status": "SELECT"},
            "big": {"type": "BIG", "name": "Big Blind", "score": HEDEF["BIG"], "status": "UPCOMING"},
            "boss": {"type": "BOSS", "name": "The Hook", "score": HEDEF["BOSS"], "status": "UPCOMING"},
        }

    # --- istemci arayüzü ---
    def saglik(self) -> bool:
        return True

    def durum(self) -> dict[str, Any]:
        """Oyunun şu anki durumunu döndürür; zamanı gelmişse gecikmeli tag paketini açar."""
        if self._paket_zamani is not None and time.monotonic() >= self._paket_zamani:
            self._paket_zamani = None  # gecikmeli olay: belirli bir süre sonra paket açılır
            self.paket = [_teklif(f"c_arcana{i}", "TAROT", 3) for i in range(3)]
            self.state = "SMODS_BOOSTER_OPENED"
            self._deste_karistir()  # tarot paketinde hedef seçilebilsin diye el dağıtılır
            self._cek()
        return copy.deepcopy(self._durum_ham())

    def _durum_ham(self) -> dict[str, Any]:
        """Durum sözlüğünü gerçek `gamestate` cevabının biçiminde kurar (kopyalanmamış)."""
        return {
            "state": self.state, "seed": self.seed, "deck": "RED", "stake": "WHITE",
            "money": self.money, "ante_num": self.ante, "round_num": self.round_no, "won": self.won,
            "round": {"hands_left": self.hands_left, "discards_left": self.discards_left,
                      "chips": self.chips, "reroll_cost": self.reroll},
            "blinds": self.blinds,
            "hand": {"cards": list(self.el), "count": len(self.el), "limit": 8},
            "cards": {"cards": list(reversed(self.deste)), "count": len(self.deste), "limit": 52},
            "jokers": {"cards": list(self.jokers), "count": len(self.jokers), "limit": 5},
            "consumables": {"cards": list(self.tuk), "count": len(self.tuk), "limit": 2},
            "shop": {"cards": self.magaza["shop"], "count": len(self.magaza["shop"])},
            "vouchers": {"cards": self.magaza["vouchers"], "count": len(self.magaza["vouchers"])},
            "packs": {"cards": self.magaza["packs"], "count": len(self.magaza["packs"])},
            "pack": {"cards": self.paket, "count": len(self.paket)},
            "hands": {}, "used_vouchers": [],
        }

    def komut(
        self, yontem: str, p: dict[str, Any] | None = None, zaman_asimi: float | None = None
    ) -> dict[str, Any]:
        """Bir oyun komutunu uygular; test için istenmişse reddeder veya cevap vermez, sonra yeni durumu döndürür.
        """
        self.cagrilar.append((yontem, p))
        if yontem in self.zorla_red:
            raise GecersizDurum(-32002, f"{yontem} reddedildi (sahte)")
        getattr(self, f"_{yontem}")(p or {})
        if yontem == "pack" and self.pack_cevapsiz:
            raise BaglantiHatasi("cevap gelmedi (sahte)")
        return self.durum()

    def _gerek(self, *fazlar: str):
        """Komutun yalnızca belirli fazlarda geçerli olmasını sağlar; değilse 'geçersiz durum' hatası verir.
        """
        if self.state not in fazlar:
            raise GecersizDurum(-32002, f"faz {self.state}, gereken {fazlar}")

    # --- komutlar ---
    def _menu(self, p):
        self._sifirla()
        self.state = "MENU"

    def _start(self, p):
        """Yeni run başlatır: seed'i kaydeder ve blind seçimine geçer."""
        self._gerek("MENU")
        self._sifirla()
        self.seed = p.get("seed", "AUTO0001")
        self.state = "BLIND_SELECT"

    def _deste_karistir(self):
        """Gerçek oyunda olduğu gibi her round başında bütün kartlar geri döner ve karışır."""
        kartlar = [_kart(i, f"{s}_{r}") for i, (s, r) in enumerate((s, r) for s in SUITS for r in RANKS)]
        random.Random(f"{self.seed}-{self.ante}-{self.round_no}").shuffle(kartlar)
        self.deste = kartlar
        self.el = []

    def _simdiki(self):
        """Seçilebilir ya da oynanmakta olan blind'ı döndürür."""
        return next(b for b in self.blinds.values() if b["status"] in ("SELECT", "CURRENT"))

    def _cek(self):
        """Eli 8 karta tamamlayacak kadar desteden kart çeker."""
        while len(self.el) < 8 and self.deste:
            self.el.append(self.deste.pop())

    def _select(self, p):
        """Blind'ı seçer: el ve discard haklarını verir, desteyi karıştırır, ilk eli dağıtır."""
        self._gerek("BLIND_SELECT")
        self._simdiki()["status"] = "CURRENT"
        self.hands_left, self.discards_left, self.chips = 4, 3, 0
        self.state = "SELECTING_HAND"
        self._deste_karistir()
        self._cek()

    def _skip(self, p):
        """Blind'ı atlar (boss atlanamaz); istenmişse tag paketini gecikmeli açacak şekilde ayarlar.
        """
        self._gerek("BLIND_SELECT")
        b = self._simdiki()
        if b["type"] == "BOSS":
            raise GecersizDurum(-32002, "boss atlanamaz")
        b["status"] = "SKIPPED"
        self._sonrakini_ac()
        if self.skip_sonrasi_gecikmeli_paket:
            self.paket_nereden = "BLIND_SELECT"  # tag paketi açıldıktan sonra blind seçimine dönülür
            self._paket_zamani = time.monotonic() + 0.2

    def _sonrakini_ac(self):
        """Sıradaki blind'ı seçilebilir yapar."""
        for ad in ("small", "big", "boss"):
            if self.blinds[ad]["status"] == "UPCOMING":
                self.blinds[ad]["status"] = "SELECT"
                return

    def _indeksler(self, p):
        """Komutun kart indekslerini doğrular (1-5 tekil ve geçerli indeks)."""
        idx = p.get("cards")
        if not idx or len(set(idx)) != len(idx) or any(not 0 <= i < len(self.el) for i in idx) or len(idx) > 5:
            raise GecersizIstek(-32001, "geçersiz kart indeksi")
        return idx

    def _play(self, p):
        """Kartları oynar: skor ekler, blind'ın bitip bitmediğini ve run'ın kazanılıp kaybedilmediğini belirler.
        """
        self._gerek("SELECTING_HAND")
        idx = self._indeksler(p)
        self.chips += 20 * len(idx)
        self.hands_left -= 1
        self.el = [c for i, c in enumerate(self.el) if i not in idx]
        b = self._simdiki()
        if self.chips >= b["score"]:
            b["status"] = "DEFEATED"
            self.el = []
            self.state = "ROUND_EVAL"
            if b["type"] == "BOSS" and self.ante >= KAZANMA_ANTE:
                self.won = True
        elif self.hands_left == 0:
            self.state = "GAME_OVER"
        else:
            self._cek()

    def _discard(self, p):
        """Kartları atar ve eli yeniden doldurur; discard hakkı yoksa hata verir."""
        self._gerek("SELECTING_HAND")
        if self.discards_left <= 0:
            raise GecersizDurum(-32002, "discard hakkı yok")
        idx = self._indeksler(p)
        self.discards_left -= 1
        self.el = [c for i, c in enumerate(self.el) if i not in idx]
        self._cek()

    def _cash_out(self, p):
        """Round ödülünü verir, mağazayı kurar ve bir sonraki blind'ı açar."""
        self._gerek("ROUND_EVAL")
        self.money += 3
        self.round_no += 1
        self.reroll = 5
        self.magaza = {
            "shop": [_teklif("j_joker", "JOKER", 4), _teklif("c_mercury", "PLANET", 3)],
            "vouchers": [_teklif("v_overstock", "VOUCHER", 10)],
            "packs": [_teklif("p_celestial", "BOOSTER", 6), _teklif("p_buffoon", "BOOSTER", 4)],
        }
        if all(self.blinds[a]["status"] in ("DEFEATED", "SKIPPED") for a in ("small", "big", "boss")):
            self.ante += 1
            self.blinds = self._yeni_blindler()
        else:
            self._sonrakini_ac()
        self.state = "SHOP"

    def _next_round(self, p):
        """Mağazadan çıkıp blind seçimine döner."""
        self._gerek("SHOP")
        self.state = "BLIND_SELECT"

    def _ode(self, fiyat):
        """Parayı düşer; yetmiyorsa hata verir."""
        if self.money < fiyat:
            raise GecersizDurum(-32002, "para yetmiyor")
        self.money -= fiyat

    def _buy(self, p):
        """Mağazadan kart, kupon veya paket satın alır (paket alınırsa paket açılır)."""
        self._gerek("SHOP")
        if "card" in p:
            k = self.magaza["shop"][p["card"]]
            self._ode(k["cost"]["buy"])
            self.magaza["shop"].pop(p["card"])
            (self.jokers if k["set"] == "JOKER" else self.tuk).append(k)
        elif "voucher" in p:
            self._ode(self.magaza["vouchers"][p["voucher"]]["cost"]["buy"])
            self.magaza["vouchers"].pop(p["voucher"])
        else:
            k = self.magaza["packs"][p["pack"]]
            self._ode(k["cost"]["buy"])
            self.magaza["packs"].pop(p["pack"])
            self.paket = [_teklif(f"c_planet{i}", "PLANET", 3) for i in range(3)]
            self.paket_nereden = "SHOP"
            self.state = "SMODS_BOOSTER_OPENED"

    def _pack(self, p):
        """Açık paketten kart seçer veya paketi atlar; hedef sayısı istenen kartlarda hedefi doğrular.
        """
        self._gerek("SMODS_BOOSTER_OPENED")
        if "card" in p and not 0 <= p["card"] < len(self.paket):
            raise GecersizIstek(-32001, "geçersiz paket kartı")
        if "card" in p:
            anahtar = self.paket[p["card"]]["key"]
            mn, mx = self.hedef_gerekir.get(anahtar, (0, 0))
            hedef = p.get("targets") or []
            if mx and not mn <= len(hedef) <= mx:
                raise GecersizIstek(
                    -32001,
                    f"Card '{anahtar}' requires {mn}-{mx} target card(s). Provided: {len(hedef)}",
                )
        self.paket_nereden = getattr(self, "paket_nereden", "SHOP")
        self.paket = []
        self.el = []
        self.state = self.paket_nereden

    def _sell(self, p):
        """Bir joker veya tüketilebilir kartı satar."""
        self._gerek("SHOP", "SELECTING_HAND")
        liste, i = (self.jokers, p["joker"]) if "joker" in p else (self.tuk, p["consumable"])
        self.money += liste.pop(i)["cost"]["sell"]

    def _reroll(self, p):
        """Mağazayı yeniler (ücreti düşer, bir sonraki ücret artar)."""
        self._gerek("SHOP")
        self._ode(self.reroll)
        self.reroll += 1

    def _use(self, p):
        """Bir tüketilebilir kartı kullanır (sahte oyunda yalnızca kartı kaldırır)."""
        self._gerek("SHOP", "SELECTING_HAND")
        self.tuk.pop(p["consumable"])
