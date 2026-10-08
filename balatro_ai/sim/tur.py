"""Tur (round) simülatörü: bir blind'ın eli oynama, discard etme ve desteden çekme akışını taklit eder.

Planlayıcı (agents/planlayici.py) karar vermek için bu simülatörde aday aksiyonlardan sonra turu sonuna kadar
oynatır (rollout) ve blind'ı geçme sıklığına bakar. Oyunun kuralları:
- Oynama veya discard sonrası el, desteden (üstten) çekilerek `el_boyu`'na tamamlanır; deste tükenirse el küçülür.
- Her oynama bir el hakkı, her discard bir discard hakkı harcar. Skor `chips >= hedef` olunca blind geçilir;
  el hakkı bitip hedef geçilmediyse tur kaybedilir.
- Skor hesabı `sim/hizli.py` ile (düz kartlar; debuff'lı kartın chip'i 0; boss taban etkileri `el_degerleri`ne
  önceden işlenir). Joker, geliştirilmiş kart ve eldeki kart efektleri simüle edilmez.

Rollout politikası (`politika`) GEÇİCİ bir tahmindir: bu bir "temel oyun" yaklaşımıdır, asıl karar planlayıcıdadır.
İleride öğrenilmiş bir politika/değer ağı ile değiştirilecektir (docs/PLAN.md, Bölüm 7).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from balatro_ai.sim.hizli import en_iyi_oynanis
from balatro_ai.sim.kartlar import Kart

KAYIP_AGIRLIK = 0.25  # tur kaybedilince değer: bu ağırlık x (ulaşılan skor / hedef); kazanma = 1.0 (+ kalan el payı)
KAYIP_USSU = 3  # kayıp değerinde ilerleme oranının üssü: dışbükey olduğu için kazanma şansı olan yüksek varyanslı oynanışı ödüllendirir
KALAN_EL_AGIRLIK = 0.03  # kazanınca her kullanılmayan el için küçük bonus (oyun kullanılmayan her ele para verir); eşitlik bozucu, tahmin
MAKS_CEKILIS = 5  # bir discard'ta en fazla 5 kart atılır


@dataclass
class Tur:
    """Simülasyondaki turun durumu: el, kalan deste (üst kart = son eleman), haklar, skor ve hedef."""

    el: list[Kart]
    deste: list[Kart]
    kalan_el: int
    kalan_discard: int
    chips: float
    hedef: float
    el_degerleri: dict[str, tuple[float, float]]
    el_boyu: int = 8
    tam_bes: bool = False  # The Psychic: yalnızca tam 5 kartlık oynanış puan getirir

    def kopya(self) -> Tur:
        """Durumun bağımsız bir kopyasını döndürür (rollout orijinali bozmasın)."""
        return Tur(
            list(self.el), list(self.deste), self.kalan_el, self.kalan_discard, self.chips,
            self.hedef, self.el_degerleri, self.el_boyu, self.tam_bes,
        )

    def chipler(self) -> list[int]:
        """Eldeki kartların chip değerleri (debuff'lı kart 0)."""
        return [k.chip for k in self.el]

    def kazandi(self) -> bool:
        """Blind geçildi mi (skor hedefe ulaştı mı)."""
        return self.chips >= self.hedef

    def bitti(self) -> bool:
        """Tur sona erdi mi: blind geçildi, el hakkı bitti veya oynanacak kart kalmadı."""
        return self.kazandi() or self.kalan_el <= 0 or not self.el

    def doldur(self) -> None:
        """Eli desteden çekerek `el_boyu`'na tamamlar (deste tükenirse el küçük kalır)."""
        while len(self.el) < self.el_boyu and self.deste:
            self.el.append(self.deste.pop())


def en_iyi(t: Tur) -> tuple[int, tuple[int, ...]]:
    """Eldeki en iyi oynanışın skoru ve kart indeksleri; The Psychic'te oynanış 5 karta tamamlanır (skor değişmez)."""
    skor, idx = en_iyi_oynanis(t.el, t.el_degerleri, t.chipler())
    if t.tam_bes:
        if len(t.el) < 5:
            return 0, tuple(range(len(t.el)))  # 5 kart oynanamaz: bu el sıfır puan
        dolgu = sorted((i for i in range(len(t.el)) if i not in idx), key=lambda i: t.el[i].chip)
        idx = tuple(sorted(idx + tuple(dolgu[: 5 - len(idx)])))
    return skor, idx


def alt_kume_skoru(t: Tur, idx: tuple[int, ...]) -> int:
    """Seçilen kartları oynamanın skoru (seçilen kümenin en iyi puanlayan altkümesi; düz kartlarda tam skordur)."""
    if t.tam_bes and len(idx) != 5:
        return 0
    secili = [t.el[i] for i in idx]
    return en_iyi_oynanis(secili, t.el_degerleri, [k.chip for k in secili])[0]


def _cikar(t: Tur, idx: tuple[int, ...]) -> None:
    """Verilen indeksli kartları elden çıkarır."""
    atilan = set(idx)
    t.el = [k for i, k in enumerate(t.el) if i not in atilan]


def oyna(t: Tur, idx: tuple[int, ...], skor: int) -> None:
    """Kartları oynar: skoru ekler, bir el hakkı harcar, eli tamamlar."""
    t.chips += skor
    t.kalan_el -= 1
    _cikar(t, idx)
    t.doldur()


def at(t: Tur, idx: tuple[int, ...]) -> None:
    """Kartları atar: bir discard hakkı harcar, eli tamamlar."""
    t.kalan_discard -= 1
    _cikar(t, idx)
    t.doldur()


def deger(t: Tur) -> float:
    """Turun sonundaki değer: blind geçildiyse 1.0 + kalan el payı, geçilmediyse küçük bir ilerleme payı (eşit olasılıklarda ayırt etmek için)."""
    if t.kazandi():
        return 1.0 + KALAN_EL_AGIRLIK * max(t.kalan_el, 0)
    return KAYIP_AGIRLIK * min(t.chips / t.hedef, 1.0) ** KAYIP_USSU


def discard_adaylari(t: Tur, oynanis: tuple[int, ...]) -> list[tuple[int, ...]]:
    """Rollout politikasının değerlendireceği az sayıda, çeşitli discard önerisi (hepsi tek ölçütle elenir: beklenen skor).

    Öneriler: en iyi oynanışın dışındakiler, en kalabalık renk dışındakiler, straight penceresi dışındakiler, en düşük
    chip'li 3-5 kart. Bunlar yalnızca öneridir; hangisinin seçileceğine örneklemeyle bulunan beklenen skor karar verir.
    """
    n = len(t.el)
    chip = t.chipler()
    ham: list[list[int]] = []
    ham.append([i for i in range(n) if i not in oynanis])
    renk_say: dict[str, list[int]] = {}
    for i, k in enumerate(t.el):
        renk_say.setdefault(k.renk, []).append(i)
    en_renk = max(renk_say.values(), key=len)
    if len(en_renk) >= 3:
        ham.append([i for i in range(n) if i not in en_renk])
    rutbe_say: dict[str, list[int]] = {}
    for i, k in enumerate(t.el):
        rutbe_say.setdefault(k.rutbe, []).append(i)
    ham.append([i for i in range(n) if i not in oynanis and len(rutbe_say[t.el[i].rutbe]) == 1])
    sirali = sorted(range(n), key=lambda i: chip[i])
    for k in (3, 4, 5):
        ham.append(sirali[:k])
    sonuc: list[tuple[int, ...]] = []
    gorulen: set[tuple[int, ...]] = set()
    for g in ham:
        g = sorted(g, key=lambda i: chip[i])[:MAKS_CEKILIS]  # en fazla 5: en düşük chip'liler
        anahtar = tuple(sorted(g))
        if anahtar and anahtar not in gorulen:
            gorulen.add(anahtar)
            sonuc.append(anahtar)
    return sonuc


def politika(t: Tur, rng: random.Random, ornek: int = 3) -> tuple[str, tuple[int, ...], int]:
    """Rollout için temel oyun: blind'ı bitiren oynanış varsa onu oyna; yoksa en iyi discard önerisi beklenen skoru
    artırıyorsa (son elde: geçme olasılığını artırıyorsa) discard et; aksi halde en iyi eli oyna."""
    skor, idx = en_iyi(t)
    kalan = t.hedef - t.chips
    if skor >= kalan or t.kalan_discard <= 0 or not t.deste:
        return "oyna", idx, skor
    son_el = t.kalan_el <= 1
    en_aday: tuple[int, ...] | None = None
    en_olcut = 0.0 if son_el else float(skor)
    cekis = min(MAKS_CEKILIS, len(t.deste))
    ornekler = [rng.sample(t.deste, cekis) for _ in range(ornek)]
    for atilacak in discard_adaylari(t, idx):
        atilan = set(atilacak)
        kalanlar = [k for i, k in enumerate(t.el) if i not in atilan]
        toplam, gecen = 0.0, 0
        for o in ornekler:
            yeni = kalanlar + o[: len(atilacak)]
            s = en_iyi_oynanis(yeni, t.el_degerleri, [k.chip for k in yeni])[0]
            toplam += s
            gecen += s >= kalan
        olcut = gecen / ornek if son_el else toplam / ornek
        if olcut > en_olcut:
            en_olcut, en_aday = olcut, atilacak
    if en_aday is not None:
        return "at", en_aday, 0
    return "oyna", idx, skor


def rollout(t: Tur, rng: random.Random) -> float:
    """Turu temel politikayla sonuna kadar oynatır ve sonundaki değeri (`deger`) döndürür; `t` değişir."""
    while not t.bitti():
        eylem, idx, skor = politika(t, rng)
        if eylem == "oyna":
            oyna(t, idx, skor)
        else:
            at(t, idx)
    return deger(t)
