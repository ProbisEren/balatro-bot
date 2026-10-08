"""Planlayıcı ajan: el ve discard kararını tur simülatöründe rollout ile verir (docs/PLAN.md, Bölüm 6-7).

Her kararda:
1. Gözlemden bir "dünya kümesi" kurar: kalan destenin rastgele çekiliş sıraları ve (varsa) yüzü kapalı kartların,
   görülenle tutarlı rastgele kimlikleri (determinizasyon). Bot yalnızca insanın görebildiği bilgiyi kullanır.
2. Tüm 1-5 kartlık oynama ve atma eylemlerini ucuz ölçütlerle sıralar ve az sayıda aday seçer. Adaylar üç farklı
   ölçütle seçilir (anlık skor, oynadıktan sonra elin potansiyeli, atınca elin potansiyeli); böylece "zayıf eli
   oynayıp kart döndürmek" gibi eylemler de aday olur. Seçimi bu ölçütler yapmaz, yalnızca öneri üretir.
3. Her adayı aynı dünyalarda turun sonuna kadar oynatır (`sim/tur.py` rollout) ve blind'ı geçme sıklığına bakar.
   Adaylar art arda yarılanarak elenir (successive halving); en yüksek değerli eylem seçilir.

Elle yazılmış strateji kuralı yoktur; tek sabit parçalar rollout politikası (geçici, bkz. sim/tur.py) ve aday
önerme ölçütleridir. Mağaza, paket ve blind kararları şimdilik sabit kuraldır (GreedyAjan'dan miras).
"""

from __future__ import annotations

import random
import time
from typing import Any

from balatro_ai.agents.greedy import GreedyAjan
from balatro_ai.env import aksiyonlar
from balatro_ai.sim import boss as boss_kurallari
from balatro_ai.sim import gezegen as gezegen_modulu
from balatro_ai.sim import jokerler as joker_modulu
from balatro_ai.sim import magaza as magaza_modulu
from balatro_ai.sim.hizli import en_iyi_oynanis
from balatro_ai.sim.kartlar import RUTBE_ID, Kart, apiden
from balatro_ai.sim.puan import EL_TABLOSU
from balatro_ai.sim.tur import Tur, alt_kume_skoru, at, en_iyi, oyna, rollout
from balatro_ai.sim.tur import deger as tur_degeri

STANDART_DESTE = tuple(Kart(r, s) for s in "SHCD" for r in RUTBE_ID)
ON_FILTRE_DUNYA = 6  # aday önerirken kullanılan dünya sayısı


def _duz(k: Kart) -> Kart:
    """Geliştirilmiş kartları düz kopyasıyla değiştirir (simülasyon düz kart varsayar); debuff bayrağı korunur."""
    return Kart(k.rutbe, k.renk, debuff=k.debuff)


class PlanlayiciAjan(GreedyAjan):
    """El ve discard kararlarını rollout ile veren ajan; diğer aşamalar GreedyAjan'ın sabit kuralıdır."""

    tur = "planlayici"

    def __init__(self, tohum: int, dunya: int = 32, butce_sn: float = 2.0, aday_sayisi: int = 18, magaza: bool = True, joker_toplama: bool = False):
        """`dunya`: değerlendirme dünyası sayısı; `butce_sn`: karar başına rollout süre sınırı; `aday_sayisi`: rollout'a girecek aday sayısı."""
        super().__init__(tohum, magaza=magaza)
        self.dunya = dunya
        self.butce_sn = butce_sn
        self.aday_sayisi = aday_sayisi
        self.joker_toplama = joker_toplama  # VERİ TOPLAMA modu: mağazada değerlendirmeden joker satın alır (doğrulama verisi için)
        self._izle: dict[str, Any] | None = None  # son kararın izi (gizli kart havuzunu hesaplamak için)
        self._kullanilan: set[tuple[str, str]] = set()  # bu turda oynanan/atılan, kimliği görülmüş kartlar
        self._son_el: dict[str, Any] | None = None  # son el aramasının sonucu (denetim için loga yazılır)

    def bilgi(self) -> dict[str, Any]:
        """Run kaydındaki `ajan` alanına yazılacak kimlik ve ayarlar."""
        return {
            "tur": self.tur, "model_id": None, "rng_tohumu": self.tohum, "dunya": self.dunya,
            "butce_sn": self.butce_sn, "aday_sayisi": self.aday_sayisi, "magaza": self.magaza,
            "joker_toplama": self.joker_toplama, "para_degeri": magaza_modulu.PARA_DEGERI, "sonraki_blind": magaza_modulu.SONRAKI_BLIND,
        }

    # ------------------------------------------------------------------ gözlemden simülasyon girdileri
    @staticmethod
    def _taban_degerleri(g: dict[str, Any], boss: str | None) -> dict[str, tuple[float, float]]:
        """Oyundaki güncel el değerleri; boss'un taban etkisi (The Flint, The Arm) işlenmiş olarak."""
        sonuc: dict[str, tuple[float, float]] = {}
        for tur, v in (g.get("hands") or {}).items():
            c, m = float(v["chips"]), float(v["mult"])
            if boss == "The Arm" and v.get("level", 1) > 1:
                _, _, lc, lm = EL_TABLOSU[tur]
                c, m = c - lc, max(m - lm, 1.0)
            sonuc[tur] = boss_kurallari.taban_degistir(boss, c, m)
        return sonuc

    def _izlerden_kullanilanlar(self, tur_kimligi: tuple) -> set[tuple[str, str]]:
        """Bu turda daha önce oynadığımız/attığımız (kimliği görülen) kartları, önceki kararın izinden günceller ve döndürür."""
        if self._izle is None or self._izle["tur_kimligi"] != tur_kimligi:
            self._kullanilan = set()  # yeni tur: iz sıfırlanır
        else:
            for i in self._izle["secilen"]:
                k = self._izle["el"][i]
                if k is not None:
                    self._kullanilan.add((k.rutbe, k.renk))
        self._izle = None  # bu iz tüketildi
        return self._kullanilan

    def _gizli_havuzu(self, el: list[Kart | None], deste: list[Kart], kullanilan: set[tuple[str, str]]) -> list[Kart]:
        """Yüzü kapalı kartların olabileceği kimlikler: standart destenin görülmeyen kartları (destede, elde veya oynanmış olmayanlar)."""
        gorulen = {(k.rutbe, k.renk) for k in deste} | {(k.rutbe, k.renk) for k in el if k is not None} | kullanilan
        havuz = [k for k in STANDART_DESTE if (k.rutbe, k.renk) not in gorulen]
        if len(havuz) < sum(k is None for k in el):  # iz eksikse: yalnızca eldekiler ve destedekiler hariç tut
            gorulen = {(k.rutbe, k.renk) for k in deste} | {(k.rutbe, k.renk) for k in el if k is not None}
            havuz = [k for k in STANDART_DESTE if (k.rutbe, k.renk) not in gorulen] or list(STANDART_DESTE)
        return havuz

    def _dunyalar(
        self, el: list[Kart | None], deste: list[Kart], havuz: list[Kart], boss: str | None, rng: random.Random,
        sayi: int | None = None,
    ) -> list[tuple[list[Kart], list[Kart]]]:
        """`sayi` (varsayılan `dunya`) adet (dolu el, karışık deste) çifti üretir: kapalı kartlara havuzdan kimlik atanır, deste karıştırılır."""
        dunyalar = []
        for _ in range(sayi or self.dunya):
            kapali = [k for k in rng.sample(havuz, min(sum(x is None for x in el), len(havuz)))]
            kapali = boss_kurallari.kartlara_uygula(boss, kapali)
            it = iter(kapali)
            dolu = [k if k is not None else next(it, Kart("2", "S")) for k in el]
            d = list(deste)
            rng.shuffle(d)
            dunyalar.append((dolu, d))
        return dunyalar

    @staticmethod
    def _jokerler(g: dict[str, Any]) -> tuple[joker_modulu.Joker, ...]:
        """Elde taşınan jokerlerin etkisi tanımlı olanları (bilinmeyenler hesapta yok sayılır, açıklamada bildirilir)."""
        tum = [joker_modulu.apiden(c) for c in (g.get("jokers") or {}).get("cards", []) if c.get("key")]
        return tuple(j for j in tum if joker_modulu.desteklenen_mi(j))

    @staticmethod
    def _baglam(g: dict[str, Any]) -> joker_modulu.Baglam:
        """Jokerlerin baktığı durum bilgisi: para ve el türlerinin oynanma sayaçları (oyun durumundan)."""
        sayaclar = {
            t: (int(v.get("played", 0)), int(v.get("played_this_round", 0))) for t, v in (g.get("hands") or {}).items()
        }
        return joker_modulu.Baglam(para=int(g.get("money") or 0), sayaclar=sayaclar)

    # ------------------------------------------------------------------ mağaza ve paket kararı
    def _magaza_karari(self, g: dict[str, Any], gecerli: set[int]) -> int | None:
        """Mağazada ve açık gezegen paketinde karar: yalnızca markette/pakette görünen öğeler arasından, her birinin sonraki
        blind'ları geçme ihtimaline etkisini rollout ile ölçüp maliyetiyle (fiyat + kaybedilen faiz) karşılaştırır.

        Şimdilik gezegenler ve etkisi `sim/jokerler.py`'de tanımlı jokerler değerlendirilir; etkisi tanımsız öğeler (diğer
        jokerler, tarot, kupon, diğer paketler) alınmaz. None döndürmek "alma, mağazadan çık / paketi atla" demektir (sabit kural).
        """
        faz = g.get("state")
        deste = [_duz(apiden(c)) for c in (g.get("cards") or {}).get("cards", [])]
        if not deste:
            return None
        degerler = {t: (float(v["chips"]), float(v["mult"])) for t, v in (g.get("hands") or {}).items()}
        hedefler = magaza_modulu.sonraki_hedefler(g.get("blinds") or {}, int(g.get("ante_num") or 1), stake=g.get("stake") or "WHITE")
        rnd = g.get("round") or {}
        el_hakki, discard_hakki = int(rnd.get("hands_left") or 4), int(rnd.get("discards_left") or 4)
        el_boyu = int((g.get("hand") or {}).get("limit") or 8)
        rng = random.Random(self._rng.random())
        desteler = magaza_modulu.desteler_uret(deste, len(hedefler), rng)

        sahip = self._jokerler(g)
        jbaglam = self._baglam(g)

        def beklenen(d: dict[str, tuple[float, float]], jk: tuple[joker_modulu.Joker, ...] | None = None) -> float:
            """Verilen el değerleri ve jokerlerle sonraki blind'ların beklenen geçilme toplamı (jk verilmezse elde olanlar)."""
            return magaza_modulu.beklenen_gecilen_blind(
                desteler, d, hedefler, el_hakki, discard_hakki, el_boyu, sahip if jk is None else jk, jbaglam
            )

        taban = beklenen(degerler)
        etki: dict[str, float] = {}

        def gezegen_etkisi(anahtar: str) -> float:
            """Gezegenin sonraki blind'ları geçme beklentisine katkısı (aynı çekilişlerle, önbellekli)."""
            if anahtar not in etki:
                etki[anahtar] = beklenen(gezegen_modulu.yukselt(degerler, gezegen_modulu.GEZEGEN_EL[anahtar])) - taban
            return etki[anahtar]

        aciklama: dict[str, Any] = {"hedefler": hedefler, "taban_beklenen": round(taban, 3)}
        if faz in aksiyonlar.PAKET_FAZLARI:  # açık paket: en çok katkı veren gezegeni seç
            adaylar = [
                (gezegen_etkisi(c["key"]), i) for i, c in enumerate((g.get("pack") or {}).get("cards", []))
                if c.get("key") in gezegen_modulu.GEZEGEN_EL
            ]
            if not adaylar:
                return None
            en = max(adaylar)
            aciklama.update(karar="paketten_gezegen", etki=round(en[0], 4))
            self.son_aciklama = aciklama
            a = aksiyonlar._PAKET_SEC + en[1]
            return a if a in gecerli else None
        for i, c in enumerate((g.get("consumables") or {}).get("cards", [])):  # elde gezegen: kullan
            if c.get("key") in gezegen_modulu.GEZEGEN_EL and aksiyonlar._KULLAN + i in gecerli:
                aciklama["karar"] = "gezegen_kullan"
                self.son_aciklama = aciklama
                return aksiyonlar._KULLAN + i
        para = int(g.get("money") or 0)
        adaylar2: list[tuple[float, int, str]] = []  # (net değer, aksiyon, ad)
        magaza_kartlari = (g.get("shop") or {}).get("cards", [])[: aksiyonlar.MAKS_MAGAZA_KART]
        if self.joker_toplama:  # VERİ TOPLAMA: değerlendirmeden joker al (etkisi tanımlı olanları tercih ederek)
            alinabilir = [
                (joker_modulu.desteklenen_mi(joker_modulu.apiden(c)), i) for i, c in enumerate(magaza_kartlari)
                if str(c.get("key", "")).startswith("j_") and c["cost"]["buy"] <= para and aksiyonlar._AL_KART + i in gecerli
            ]
            if alinabilir:
                tercih = [i for ok, i in alinabilir if ok] or [i for _, i in alinabilir]
                i = rng.choice(tercih)
                aciklama.update(karar=f"veri_toplama_joker:{magaza_kartlari[i]['key']}")
                self.son_aciklama = aciklama
                return aksiyonlar._AL_KART + i
        for i, c in enumerate(magaza_kartlari):  # markette görünen joker: etkisi tanımlıysa değeri hesapla
            fiyat = c["cost"]["buy"]
            if str(c.get("key", "")).startswith("j_") and fiyat <= para and aksiyonlar._AL_KART + i in gecerli:
                joker = joker_modulu.apiden(c)
                if joker_modulu.desteklenen_mi(joker):
                    delta = beklenen(degerler, (*sahip, joker)) - taban
                    adaylar2.append((delta - magaza_modulu.maliyet(para, fiyat), aksiyonlar._AL_KART + i, c["key"]))
        for i, c in enumerate(magaza_kartlari):
            fiyat = c["cost"]["buy"]
            if c.get("key") in gezegen_modulu.GEZEGEN_EL and fiyat <= para and aksiyonlar._AL_KART + i in gecerli:
                adaylar2.append((gezegen_etkisi(c["key"]) - magaza_modulu.maliyet(para, fiyat), aksiyonlar._AL_KART + i, c["key"]))
        for i, c in enumerate((g.get("packs") or {}).get("cards", [])[: aksiyonlar.MAKS_MAGAZA_PAKET]):
            parcalar = c.get("key", "").split("_")  # p_celestial_normal_1
            fiyat = c["cost"]["buy"]
            if len(parcalar) >= 3 and parcalar[1] == "celestial" and fiyat <= para and aksiyonlar._AL_PAKET + i in gecerli:
                deltalar = {k: gezegen_etkisi(k) for k in gezegen_modulu.YAYGIN_GEZEGENLER}
                beklenen_etki = gezegen_modulu.paket_beklenen_degeri(deltalar, parcalar[2], rng)
                adaylar2.append((beklenen_etki - magaza_modulu.maliyet(para, fiyat), aksiyonlar._AL_PAKET + i, c["key"]))
        aciklama["adaylar"] = [(round(v, 4), ad) for v, _, ad in sorted(adaylar2, reverse=True)[:5]]
        if adaylar2:
            net, a, ad = max(adaylar2)
            if net > 0:
                aciklama.update(karar=f"satin_al:{ad}", net=round(net, 4))
                self.son_aciklama = aciklama
                return a
        aciklama["karar"] = "magazadan_cik"
        self.son_aciklama = aciklama
        return None

    # ------------------------------------------------------------------ karar
    def _el_karari(self, g: dict[str, Any], gecerli: set[int]) -> int | None:
        """SELECTING_HAND'de en iyi oynama veya atma eylemini rollout ile seçer; aksiyon kimliğini döndürür."""
        t0 = time.monotonic()
        rnd = g.get("round") or {}
        siradaki = next((b for b in (g.get("blinds") or {}).values() if b.get("status") == "CURRENT"), {})
        boss = siradaki.get("name") if siradaki.get("type") == "BOSS" else None
        hedef = float(siradaki.get("score") or 0)
        chips = float(rnd.get("chips", 0))
        # Elde yüzü kapalı kartlar `None` olarak kalır; kimlikleri dünyalarda örneklenir.
        ham_el = (g["hand"]["cards"])[: aksiyonlar.MAKS_EL]
        el = [_duz(apiden(c)) if "key" in c else None for c in ham_el]
        n = len(el)
        deste = boss_kurallari.kartlara_uygula(
            boss, [_duz(apiden(c)) for c in (g.get("cards") or {}).get("cards", [])]
        )
        el = [boss_kurallari.kartlara_uygula(boss, [k])[0] if k is not None else None for k in el]
        taban = self._taban_degerleri(g, boss)
        tur_kimligi = (g.get("ante_num"), g.get("round_num"))
        kullanilan = self._izlerden_kullanilanlar(tur_kimligi)
        havuz = self._gizli_havuzu(el, deste, kullanilan)
        rng = random.Random(self._rng.random())
        dunyalar = self._dunyalar(el, deste, havuz, boss, rng)
        hl, dl = int(rnd.get("hands_left", 0)), int(rnd.get("discards_left", 0))
        jokerler = self._jokerler(g)
        jbaglam = self._baglam(g)
        el_boyu = int((g["hand"].get("limit")) or 8)

        def yeni_tur(j: int) -> Tur:
            """j. dünyanın başlangıç turunu kurar."""
            dolu, d = dunyalar[j]
            return Tur(
                list(dolu), list(d), hl, dl, chips, hedef, taban, el_boyu, tam_bes=boss == "The Psychic",
                jokerler=jokerler, baglam=jbaglam,
            )

        kombinasyonlar = [c for c in aksiyonlar.KOMBINASYONLAR if c[-1] < n]
        self._son_el = None
        if hl <= 1 and dl > 0:  # son el: oynayarak kazanılamıyorsa discard'ın küçük şansı bile değerlidir
            a = self._son_el_ara(el, deste, havuz, boss, rng, yeni_tur, kombinasyonlar, hedef - chips, gecerli, tur_kimligi)
            if a is not None:
                return a
        adaylar = self._aday_oner(yeni_tur, kombinasyonlar, hl, dl, hedef - chips)
        aciklama: dict[str, Any] = {
            "kalan_hedef": hedef - chips, "dunya": self.dunya, "gizli_kart": sum(k is None for k in el),
            "aday_sayisi": len(adaylar),
        }
        if not adaylar:
            self.son_aciklama = {**aciklama, "karar": "aday_yok"}
            return None
        if self._son_el:
            aciklama["son_el_arama"] = self._son_el
        sonuc = self._ele(yeni_tur, adaylar, t0)
        en = sonuc[0]
        eylem, idx = en["eylem"]
        a = (aksiyonlar._OYNA if eylem == "oyna" else aksiyonlar._AT) + aksiyonlar.KOMBINASYONLAR.index(idx)
        aciklama.update(
            karar=f"{eylem}_rollout", p_kazanma=round(en["kazanma"], 3), deger=round(en["deger"], 3),
            rollout_sayisi=sum(x["n"] for x in sonuc), sure_ms=round((time.monotonic() - t0) * 1000),
            ilk_adaylar=[
                {"eylem": x["eylem"][0], "kartlar": list(x["eylem"][1]), "n": x["n"],
                 "p_kazanma": round(x["kazanma"], 3), "deger": round(x["deger"], 3)}
                for x in sonuc[:6]
            ],
        )
        self.son_aciklama = aciklama
        self._izle = {"tur_kimligi": tur_kimligi, "el": el, "secilen": idx}
        return a if a in gecerli else None

    def _son_el_ara(self, el, deste, havuz, boss, rng, yeni_tur, kombinasyonlar, kalan, gecerli, tur_kimligi) -> int | None:
        """Son el ve discard hakkı varken: mevcut en iyi oynanış blind'ı bitirmiyorsa, her discard kümesinin ardından
        blind'ı bitirebilme olasılığını (çok sayıda dünyada) hesaplar; en yüksek olasılık sıfırdan büyükse o discard'ı seçer.

        Oynayarak kazanma olasılığı sıfırken (görünen kartlarla kesin kayıp) discard etmek her zaman en az eşit iyidir.
        Hiçbir discard şansı yoksa None döner ve normal akış (rollout) en iyi eli oynatır.
        """
        sayi = max(self.dunya, 64)
        sablon = yeni_tur(0)  # haklar, hedef ve taban değerleri bu şablondan kopyalanır
        turlar = []
        for dolu, d in self._dunyalar(el, deste, havuz, boss, rng, sayi):
            t = sablon.kopya()
            t.el, t.deste = list(dolu), list(d)
            turlar.append(t)
        oyna_p = sum(en_iyi(t)[0] >= kalan for t in turlar) / sayi  # eldeki en iyi oynanışla kazanma oranı
        self._son_el = {"oynayarak_kazanma": round(oyna_p, 3), "dunya": sayi}
        if oyna_p >= 1.0:
            return None
        en_p, en_c = 0.0, None
        for c in kombinasyonlar:  # her discard kümesi: sonrasında en iyi oynanış blind'ı bitirir mi
            gecen = 0
            for t in turlar:
                k = t.kopya()
                _cikar_ve_doldur(k, c)
                gecen += en_iyi(k)[0] >= kalan
            if gecen / sayi > en_p:
                en_p, en_c = gecen / sayi, c
        self._son_el["discard_ile_kazanma"] = round(en_p, 3)
        if en_c is None or oyna_p >= en_p:
            return None
        a = aksiyonlar._AT + aksiyonlar.KOMBINASYONLAR.index(en_c)
        self.son_aciklama = {
            "karar": "son_el_discard", "kalan_hedef": kalan, "son_el_arama": self._son_el, "kartlar": list(en_c),
        }
        self._izle = {"tur_kimligi": tur_kimligi, "el": el, "secilen": en_c}
        return a if a in gecerli else None

    def _aday_oner(self, yeni_tur, kombinasyonlar, hl: int, dl: int, kalan: float) -> list[tuple[str, tuple[int, ...]]]:
        """Tüm oynama/atma eylemlerini ucuz ölçütlerle sıralayıp rollout'a girecek az sayıda aday seçer.

        Ölçütler (hepsi `ON_FILTRE_DUNYA` dünyada ortalama): oynama için anlık skor; oynama için skor + oynadıktan
        sonraki elin en iyi skoru; atma için atıştan sonraki elin en iyi skoru. Her ölçütün en iyilerinin birleşimi.
        """
        s0 = min(ON_FILTRE_DUNYA, self.dunya)
        turlar = [yeni_tur(j) for j in range(s0)]
        oynanabilir = [c for c in kombinasyonlar if not (turlar[0].tam_bes and len(c) != 5)]
        imdt: dict[tuple[int, ...], float] = {}
        pot: dict[tuple[int, ...], float] = {}
        garanti: list[tuple[float, tuple[int, ...]]] = []
        for c in oynanabilir:
            ss = [alt_kume_skoru(t, c) for t in turlar]
            imdt[c] = sum(ss) / s0
            if min(ss) >= kalan:
                garanti.append((imdt[c], c))
        if garanti:  # her dünyada blind'ı bitiren oynanış var: en yüksek skorlusunu oyna
            return [("oyna", max(garanti)[1])]
        for c in kombinasyonlar:  # oynadıktan/attıktan sonra elin potansiyeli
            toplam = 0.0
            for t in turlar:
                k = t.kopya()
                _cikar_ve_doldur(k, c)
                toplam += en_iyi_oynanis(k.el, k.el_degerleri, k.chipler(), k.jokerler, k.joker_baglami())[0] if k.el else 0
            pot[c] = toplam / s0
        oyun_siralama = sorted(oynanabilir, key=lambda c: imdt[c], reverse=True)
        potansiyelli = sorted(oynanabilir, key=lambda c: imdt[c] + (pot[c] if hl > 1 else 0), reverse=True)
        adaylar: list[tuple[str, tuple[int, ...]]] = []
        for c in oyun_siralama[:6] + potansiyelli[:6]:
            if ("oyna", c) not in adaylar:
                adaylar.append(("oyna", c))
        if dl > 0:
            for c in sorted(kombinasyonlar, key=lambda c: pot[c], reverse=True)[:8]:
                adaylar.append(("at", c))
        return adaylar[: self.aday_sayisi]

    def _ele(self, yeni_tur, adaylar, t0: float) -> list[dict[str, Any]]:
        """Adayları aynı dünyalarda turun sonuna kadar oynatıp art arda yarılayarak eler; değere göre sıralı sonuç döndürür."""
        durum = [{"eylem": a, "toplam": 0.0, "kazandi": 0, "n": 0} for a in adaylar]
        hayatta = list(durum)
        j0 = 0
        adim = 4  # ilk turda her aday için dünya sayısı; her turda iki katına çıkar
        while hayatta and j0 < self.dunya:
            j1 = min(j0 + adim, self.dunya)
            for d in hayatta:
                eylem, idx = d["eylem"]
                for j in range(j0, j1):
                    t = yeni_tur(j)
                    if eylem == "oyna":
                        oyna(t, idx, alt_kume_skoru(t, idx))
                    else:
                        at(t, idx)
                    r = random.Random(j * 7919 + 13)
                    d["toplam"] += rollout(t, r) if not t.bitti() else tur_degeri(t)
                    d["kazandi"] += t.kazandi()
                    d["n"] += 1
            for d in hayatta:
                d["deger"] = d["toplam"] / max(d["n"], 1)
                d["kazanma"] = d["kazandi"] / max(d["n"], 1)
            hayatta.sort(key=lambda d: (d["deger"], d["kazanma"]), reverse=True)
            j0, adim = j1, adim * 2
            if time.monotonic() - t0 > self.butce_sn or len(hayatta) == 1:
                break
            hayatta = hayatta[: max(1, (len(hayatta) + 1) // 2)]
        # Kazanan, son turu oynayan (en çok dünyada denenmiş) adaylar arasındandır; elenenler azıcık örnekle şans eseri
        # yüksek çıkmış olabilir, o yüzden sıralamada her zaman sonra gelir.
        for d in durum:
            d.setdefault("deger", 0.0)
            d.setdefault("kazanma", 0.0)
        kalanlar = {id(d) for d in hayatta}
        return sorted(
            durum, key=lambda d: (id(d) in kalanlar, d["n"] >= 1, d["deger"], d["kazanma"]), reverse=True
        )


def _cikar_ve_doldur(t: Tur, idx: tuple[int, ...]) -> None:
    """Seçilen kartları elden çıkarıp eli desteden tamamlar (haklar harcanmaz); aday sıralamasında potansiyel ölçmek için."""
    atilan = set(idx)
    t.el = [k for i, k in enumerate(t.el) if i not in atilan]
    t.doldur()
