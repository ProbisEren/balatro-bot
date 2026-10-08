"""Greedy ajan (docs/PLAN.md, Bölüm 6 ve 7, basamak 2): kesin hesap + Monte Carlo discard.

El seçimi: eldeki 1-5 kartın tüm kombinasyonlarını puan motoruyla hesaplar, en yüksek skoru seçer.
Blind'ı bitiren bir oynanış varsa onu oynar. Yoksa ve discard hakkı varsa, tutulacak kart kümeleri için
destenin kalanından rastgele çekilişler (determinizasyon: bot yalnızca insanın gördüğü "kalan kartlar
listesini" bilir, sırasını bilmez) örnekleyip beklenen en iyi skoru (son elde: blind'ı geçme olasılığını)
karşılaştırır; discard daha iyiyse atar, değilse oynar.

Sınırlar (v1): jokerleri puana katmaz (puan motorunda yok), mağaza/paket/blind kararlarında sabit kural
kullanır (blind seç, mağazadan hiçbir şey almadan çık, paketleri atla), boss geçmişi (Eye/Mouth) bilinmez.
"""

from __future__ import annotations

import random
from typing import Any

from balatro_ai.env import aksiyonlar
from balatro_ai.sim import boss as boss_kurallari
from balatro_ai.sim import gezegen as gezegen_modulu
from balatro_ai.sim.hizli import en_iyi_skor, hizli_uygun_mu
from balatro_ai.sim.kartlar import Kart, apiden
from balatro_ai.sim.puan import puan_hesapla

MAKS_ADAY = 12  # tam motorla yeniden değerlendirilen en iyi discard kümesi sayısı


class GreedyAjan:
    """Greedy ajan: eldeki tüm oynanışları puan motoruyla hesaplayıp en iyisini oynar; gerekirse Monte Carlo ile discard eder.
    """
    tur = "greedy"

    def __init__(
        self,
        tohum: int,
        ornek: int = 40,
        ornek_tam: int = 8,
        magaza: bool = False,
        gezegen_esik: float = 3.0,
        gezegen_ornek: int = 300,
    ):
        """`ornek`: hızlı değerlendiriciyle çekiliş sayısı; `ornek_tam`: tam motorla (boss debuff, geliştirilmiş kart)."""
        self.tohum = tohum
        self.ornek = ornek
        self.ornek_tam = ornek_tam
        self.magaza = magaza  # False (varsayılan): mağaza kararı yok, v1 baseline'ı (hiçbir şey almadan çık); True: gezegen alır/kullanır
        self.gezegen_esik = gezegen_esik  # satın alma için gereken (puan/el artışı) / fiyat
        self.gezegen_ornek = gezegen_ornek
        self._rng = random.Random(tohum)
        self.son_aciklama: dict[str, Any] = {}

    def bilgi(self) -> dict[str, Any]:
        """Run kaydındaki `ajan` alanına yazılacak kimlik ve ayar bilgisini döndürür."""
        return {
            "tur": self.tur, "model_id": None, "rng_tohumu": self.tohum,
            "ornek": self.ornek, "ornek_tam": self.ornek_tam, "maks_aday": MAKS_ADAY,
            "magaza": self.magaza, "gezegen_esik": self.gezegen_esik, "gezegen_ornek": self.gezegen_ornek,
        }

    # ------------------------------------------------------------------ karar
    def sec(self, gozlem: dict[str, Any], bilgi: dict[str, Any]) -> int:
        gecerli = bilgi["gecerli_aksiyonlar"]
        self.son_aciklama = {}
        if gozlem.get("state") == "SELECTING_HAND" and gozlem["hand"]["cards"]:
            a = self._el_karari(gozlem, set(gecerli))
            if a is not None:
                return a
        elif self.magaza and gozlem.get("state") in ("SHOP", *aksiyonlar.PAKET_FAZLARI):
            a = self._magaza_karari(gozlem, set(gecerli))
            if a is not None:
                return a
        return self._sabit_kural(gecerli)

    # ------------------------------------------------------------------ mağaza ve paket kararı
    def _magaza_karari(self, g: dict[str, Any], gecerli: set[int]) -> int | None:
        """Mağazada ve açık pakette gezegen kararı: elde gezegen varsa kullan, değerliyse gezegen/gezegen paketi al,
        açık gezegen paketinden en değerli gezegeni seç. Başka bir şey almaz (joker, tarot, kupon: sonraki sürümler)."""
        faz = g.get("state")
        deste = [self._duz(apiden(c)) for c in (g.get("cards") or {}).get("cards", [])]
        el_degerleri = {t: (float(v["chips"]), float(v["mult"])) for t, v in (g.get("hands") or {}).items()}
        if not deste:
            return None
        eller = gezegen_modulu.ornek_eller(deste, self.gezegen_ornek, self._rng)
        deger = gezegen_modulu.gezegen_degerleri(eller, el_degerleri, list(gezegen_modulu.GEZEGEN_EL))
        aciklama: dict[str, Any] = {"gezegen_degerleri": {k: round(v, 1) for k, v in deger.items() if v}}

        if faz in aksiyonlar.PAKET_FAZLARI:  # açık paket: gezegen seç
            en = max(
                ((deger.get(c.get("key"), 0.0), i) for i, c in enumerate(g.get("pack", {}).get("cards", []))
                 if c.get("key") in gezegen_modulu.GEZEGEN_EL),
                default=(0.0, -1),
            )
            a = aksiyonlar._PAKET_SEC + en[1]
            if en[0] > 0 and a in gecerli:
                aciklama["karar"] = "paketten_gezegen"
                self.son_aciklama = aciklama
                return a
            return None  # değerli gezegen yok: sabit kural paketi atlar

        # Elde duran gezegen kartı: hemen kullan.
        for i, c in enumerate((g.get("consumables") or {}).get("cards", [])):
            if c.get("key") in gezegen_modulu.GEZEGEN_EL and aksiyonlar._KULLAN + i in gecerli:
                aciklama["karar"] = "gezegen_kullan"
                self.son_aciklama = aciklama
                return aksiyonlar._KULLAN + i
        para = g.get("money", 0)
        adaylar: list[tuple[float, int, str]] = []  # (puan/el artışı ÷ fiyat, aksiyon, ad)
        for i, c in enumerate((g.get("shop") or {}).get("cards", [])[: aksiyonlar.MAKS_MAGAZA_KART]):
            fiyat = c["cost"]["buy"]
            if c.get("key") in gezegen_modulu.GEZEGEN_EL and fiyat <= para and aksiyonlar._AL_KART + i in gecerli:
                adaylar.append((deger[c["key"]] / fiyat, aksiyonlar._AL_KART + i, c["key"]))
        for i, c in enumerate((g.get("packs") or {}).get("cards", [])[: aksiyonlar.MAKS_MAGAZA_PAKET]):
            anahtar = c.get("key", "")
            fiyat = c["cost"]["buy"]
            parcalar = anahtar.split("_")  # p_celestial_normal_1
            if len(parcalar) >= 3 and parcalar[1] == "celestial" and fiyat <= para and aksiyonlar._AL_PAKET + i in gecerli:
                beklenen = gezegen_modulu.paket_beklenen_degeri(deger, parcalar[2], self._rng)
                adaylar.append((beklenen / fiyat, aksiyonlar._AL_PAKET + i, anahtar))
        aciklama["adaylar"] = [(round(r, 2), ad) for r, _, ad in sorted(adaylar, reverse=True)[:5]]
        if adaylar:
            oran, a, ad = max(adaylar)
            if oran >= self.gezegen_esik:
                aciklama["karar"] = f"satin_al:{ad}"
                self.son_aciklama = aciklama
                return a
        aciklama["karar"] = "magazadan_cik"
        self.son_aciklama = aciklama
        return None  # sabit kural mağazadan çıkar

    def _sabit_kural(self, gecerli: list[int]) -> int:
        """El dışındaki aşamalar: blind seç, mağazadan çık, paketi atla, hiçbir şeyi satın alma."""
        tercih = ("select", "next_round")
        for a in gecerli:
            if aksiyonlar.komut(a)["yontem"] in tercih:
                return a
        for a in gecerli:
            k = aksiyonlar.komut(a)
            if k["yontem"] == "pack" and (k["parametreler"] or {}).get("skip"):
                return a
        return gecerli[0]

    # ------------------------------------------------------------------ el kararı
    def _el_karari(self, g: dict[str, Any], gecerli: set[int]) -> int | None:
        # Baseline sınırı: yüzü kapalı kartların kimliği gözlemde yoktur (`key` yok); greedy onları hesaba katamaz,
        # oynanışlarda ve tutulacak kartlarda yok sayar. Kapalı kartlarla akıl yürütme PlanlayiciAjan'dadır.
        el = [apiden(c) if "key" in c else None for c in g["hand"]["cards"][: aksiyonlar.MAKS_EL]]
        n = len(el)
        degerler = {t: (float(v["chips"]), float(v["mult"])) for t, v in g["hands"].items()}
        siradaki = next((b for b in g["blinds"].values() if b.get("status") == "CURRENT"), {})
        boss = siradaki.get("name") if siradaki.get("type") == "BOSS" else None
        kalan = (siradaki.get("score") or 0) - (g.get("round") or {}).get("chips", 0)

        # 1) Tüm kombinasyonlar tam motorla.
        sonuclar = []
        for idx, c in enumerate(aksiyonlar.KOMBINASYONLAR):
            if c[-1] >= n or any(el[i] is None for i in c):
                continue
            oy = [el[i] for i in c]
            elde = [el[i] for i in range(n) if i not in c and el[i] is not None]
            r = puan_hesapla(oy, elde, el_degerleri=degerler, boss=boss)
            sonuclar.append((r.skor, -len(c), idx, r))
        sonuclar.sort(key=lambda x: (x[0], x[1]), reverse=True)  # eşit skorda az kart
        if not sonuclar:  # elde görünen kart yok: sabit kurala bırak
            return None
        en_skor, _, en_idx, en_r = sonuclar[0]
        oyna_id = aksiyonlar._OYNA + en_idx
        aciklama: dict[str, Any] = {
            "tahmin_skor": en_skor, "tahmin_el": en_r.el_turu, "kalan_hedef": kalan,
            "en_iyi_kartlar": list(aksiyonlar.KOMBINASYONLAR[en_idx]),
            "kombinasyon_sayisi": len(sonuclar),
            "ilk_5": [(s, list(aksiyonlar.KOMBINASYONLAR[i])) for s, _, i, _ in sonuclar[:5]],
        }

        def bitir(a: int, karar: str) -> int | None:
            """Kararı ve açıklamasını kaydeder; seçilen aksiyon geçerli değilse None döner (çağıran sabit kurala düşer).
            """
            aciklama["karar"] = karar
            self.son_aciklama = aciklama
            return a if a in gecerli else None

        discards = (g.get("round") or {}).get("discards_left", 0)
        hands = (g.get("round") or {}).get("hands_left", 0)
        if en_skor >= kalan or discards <= 0:
            return bitir(oyna_id, "oyna_blind_biter" if en_skor >= kalan else "oyna_discard_yok")

        # 2) Discard: tüm discard kümeleri (1-5 kart) ortak rastgele çekilişlerle değerlendirilir.
        deste = [apiden(c) for c in g["cards"]["cards"]]
        if not deste:
            return bitir(oyna_id, "oyna_deste_bos")
        sec = self._degerlendir(el, deste, degerler, boss, kalan, hands, en_skor)
        aciklama["discard_adaylari"] = sec["ozet"]
        aciklama["simdiki"] = sec["simdiki"]
        if sec["en"] is not None and sec["metrik"] > sec["simdiki"]:
            a = aksiyonlar._AT + aksiyonlar.KOMBINASYONLAR.index(tuple(sorted(sec["en"])))
            aciklama["beklenen"] = sec["metrik"]
            return bitir(a, "discard")
        return bitir(oyna_id, "oyna_discard_daha_iyi_degil")

    @staticmethod
    def _duz(k: Kart) -> Kart:
        """Hızlı değerlendirici için geliştirmesiz kopya (aday sıralaması için yaklaşık)."""
        return Kart(k.rutbe, k.renk)

    def _degerlendir(self, el, deste, degerler, boss, kalan, hands, en_skor) -> dict[str, Any]:
        """Her discard kümesi için beklenen en iyi skoru (son elde: blind'ı geçme olasılığını) hesaplar.

        Aşama 1: bütün kümeler, hızlı değerlendirici (düz kartlar varsayımıyla) ve ortak çekilişlerle.
        Aşama 2 (boss debuff'ı veya geliştirilmiş kart varsa): en iyi MAKS_ADAY küme tam motorla yeniden.
        """
        n = len(el)
        son_el = hands <= 1
        kumeler = [c for c in aksiyonlar.KOMBINASYONLAR if c[-1] < n]
        duz_el = [self._duz(k) if k is not None else None for k in el]
        duz_deste = [self._duz(k) for k in deste]
        permutasyon_sayisi = self.ornek
        cekis = min(aksiyonlar.MAKS_KART, len(deste))
        idx_perm = [self._rng.sample(range(len(deste)), cekis) for _ in range(permutasyon_sayisi)]
        zor = boss is not None or not (hizli_uygun_mu([k for k in el if k is not None]) and hizli_uygun_mu(deste))

        def olc(tut_listesi, cekilenler_listesi, skor_fn):
            """Bir tutma kümesi için çekilişler üzerinden ortalama en iyi skoru ve blind'ı geçme oranını hesaplar.
            """
            toplam, gecen = 0.0, 0
            for cekilen in cekilenler_listesi:
                s = skor_fn(tut_listesi + cekilen)
                toplam += s
                gecen += s >= kalan
            m = len(cekilenler_listesi)
            return toplam / m, gecen / m

        sonuc = []
        for c in kumeler:
            tut = [duz_el[i] for i in range(n) if i not in c and duz_el[i] is not None]
            cekilenler = [[duz_deste[j] for j in perm[: len(c)]] for perm in idx_perm]
            ort, p = olc(tut, cekilenler, lambda x: en_iyi_skor(x, degerler))
            sonuc.append({"at": c, "beklenen": ort, "gecme": p})

        def metrik(x):
            """Küme sıralama ölçütü: son elde (geçme olasılığı, beklenen skor), diğer ellerde (beklenen skor, geçme olasılığı).
            """
            return (x["gecme"], x["beklenen"]) if son_el else (x["beklenen"], x["gecme"])

        sonuc.sort(key=metrik, reverse=True)
        if zor:
            deste_boss = boss_kurallari.kartlara_uygula(boss, deste)
            for x in sonuc[:MAKS_ADAY]:
                c = x["at"]
                tut = [el[i] for i in range(n) if i not in c and el[i] is not None]
                cekilenler = [
                    [deste_boss[j] for j in perm[: len(c)]] for perm in idx_perm[: self.ornek_tam]
                ]
                x["beklenen"], x["gecme"] = olc(tut, cekilenler, lambda y: self._tam_en_iyi(y, degerler, boss))
            sonuc = sorted(sonuc[:MAKS_ADAY], key=metrik, reverse=True)
        en = sonuc[0]
        simdiki = 0.0 if son_el else float(en_skor)
        return {
            "en": en["at"],
            "metrik": en["gecme"] if son_el else en["beklenen"],
            "simdiki": simdiki,
            "ozet": [
                {"at": list(x["at"]), "beklenen": round(x["beklenen"], 1), "gecme_olasiligi": round(x["gecme"], 3)}
                for x in sonuc[:5]
            ],
        }

    @staticmethod
    def _tam_en_iyi(kartlar: list[Kart], degerler, boss) -> int:
        """Verilen kartlardan oynanabilecek en yüksek skoru TAM puan motoruyla bulur (boss debuff'ı ve geliştirilmiş kartlar için; yavaş).
        """
        en = 0
        n = len(kartlar)
        for c in aksiyonlar.KOMBINASYONLAR:
            if c[-1] >= n:
                continue
            en = max(en, puan_hesapla([kartlar[i] for i in c], [kartlar[i] for i in range(n) if i not in c],
                                      el_degerleri=degerler, boss=boss).skor)
        return en
