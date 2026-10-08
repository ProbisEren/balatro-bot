"""Hızlı en iyi skor hesabının tam puan motoruyla aynı sonucu verdiğinin testleri."""

import itertools
import random

from balatro_ai.sim.hizli import en_iyi_skor, hizli_uygun_mu
from balatro_ai.sim.kartlar import Kart, anahtardan
from balatro_ai.sim.puan import EL_TABLOSU, puan_hesapla

DESTE = [(s, r) for s in "SHCD" for r in "23456789TJQKA"]
VARSAYILAN = {t: (float(v[0]), float(v[1])) for t, v in EL_TABLOSU.items()}


def kesin_en_iyi(el, degerler):
    """Referans: bütün 1-5 kartlık alt kümeleri tam puan motoruyla hesaplayıp en yükseği döndürür.
    """
    en = 0
    for n in range(1, min(5, len(el)) + 1):
        for alt in itertools.combinations(el, n):
            en = max(en, puan_hesapla(list(alt), el_degerleri=degerler).skor)
    return en


def test_hizli_degerlendirici_tam_motorla_ayni_rastgele_eller():
    """1500 rastgele elde hızlı değerlendiricinin tam motorla birebir aynı skoru verdiğini doğrular.
    """
    rng = random.Random(12345)
    for _ in range(1500):
        n = rng.choice([5, 6, 7, 8, 8, 8, 9, 10])
        el = [anahtardan(f"{s}_{r}") for s, r in rng.sample(DESTE, n)]
        assert hizli_uygun_mu(el)
        assert en_iyi_skor(el, VARSAYILAN) == kesin_en_iyi(el, VARSAYILAN), [f"{k.renk}{k.rutbe}" for k in el]


def test_hizli_degerlendirici_yukseltilmis_el_degerleriyle_de_ayni():
    """Seviyesi yükseltilmiş el değerleriyle de hızlı ve tam hesabın aynı olduğunu doğrular."""
    rng = random.Random(7)
    seviyeli = {**VARSAYILAN, "Pair": (40.0, 4.0), "Flush": (65.0, 8.0), "Straight": (90.0, 10.0), "High Card": (25.0, 3.0)}
    for _ in range(300):
        el = [anahtardan(f"{s}_{r}") for s, r in rng.sample(DESTE, 8)]
        assert en_iyi_skor(el, seviyeli) == kesin_en_iyi(el, seviyeli)


def test_hizli_degerlendirici_kucuk_eller_ve_ozel_durumlar():
    """Tek kart, çift, As düşük straight ve kraliyet straight flush gibi özel durumları doğrular."""
    for kartlar, beklenen in (
        (["S_A"], 16), (["S_K", "D_K"], 60), (["H_A", "D_2", "S_3", "C_4", "H_5"], 220),
        (["S_T", "S_J", "S_Q", "S_K", "S_A"], 1208),
    ):
        el = [anahtardan(k) for k in kartlar]
        assert en_iyi_skor(el, VARSAYILAN) == beklenen == kesin_en_iyi(el, VARSAYILAN)


def test_uygun_degilse_isaretler():
    """Geliştirilmiş, debuff'lı veya tekrarlı kart varsa hızlı yolun uygun değil dendiğini doğrular.
    """
    assert not hizli_uygun_mu([Kart("9", "S", gelistirme="bonus")])
    assert not hizli_uygun_mu([Kart("9", "S", debuff=True)])
    assert not hizli_uygun_mu([anahtardan("S_9"), anahtardan("S_9")])  # tekrarlı kart


def test_en_iyi_oynanis_skoru_tam_motorla_ayni_ve_secilen_kartlar_o_skoru_verir():
    """Rastgele ellerde (rastgele debuff'lı kartlarla da) `en_iyi_oynanis` skorunun tam motorla aynı olduğunu, döndürdüğü kartların gerçekten o skoru verdiğini doğrular."""
    from dataclasses import replace

    from balatro_ai.sim.hizli import en_iyi_oynanis

    rng = random.Random(99)
    for _ in range(600):
        n = rng.choice([5, 6, 7, 8, 8, 9])
        el = [anahtardan(f"{s}_{r}") for s, r in rng.sample(DESTE, n)]
        el = [replace(k, debuff=True) if rng.random() < 0.25 else k for k in el]
        skor, idx = en_iyi_oynanis(el, VARSAYILAN, [k.chip for k in el])
        assert skor == kesin_en_iyi(el, VARSAYILAN), [f"{k.renk}{k.rutbe}{'d' if k.debuff else ''}" for k in el]
        assert 1 <= len(idx) <= 5 and len(set(idx)) == len(idx)
        assert puan_hesapla([el[i] for i in idx], el_degerleri=VARSAYILAN).skor == skor
