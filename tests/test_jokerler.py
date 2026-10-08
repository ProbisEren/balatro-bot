"""Joker etkilerinin (sim/jokerler.py) testleri: elle hesaplanmış skorlar, uygulama sırası ve hızlı yolun tam motorla uyumu."""

import itertools
import random

import pytest

from balatro_ai.sim.hizli import en_iyi_oynanis
from balatro_ai.sim.jokerler import (
    ICEREN,
    TANIMLAR,
    Baglam,
    Joker,
    apiden,
    bilinmeyenler,
    desteklenen_mi,
)
from balatro_ai.sim.kartlar import anahtardan
from balatro_ai.sim.puan import EL_TABLOSU, puan_hesapla

VARSAYILAN = {t: (float(v[0]), float(v[1])) for t, v in EL_TABLOSU.items()}


def kartlar(*a):
    """Oyun anahtarlarından düz kart listesi."""
    return [anahtardan(x) for x in a]


def skor(el, *jokerler, **baglam):
    """Verilen elin (tüm kartlar oynanır) verilen jokerlerle skoru; bağlam alanları anahtar kelimeyle verilir."""
    return puan_hesapla(el, jokerler=[j if isinstance(j, Joker) else Joker(j) for j in jokerler], baglam=Baglam(**baglam)).skor


PAIR9 = ["S_9", "D_9"]  # taban: (10 + 9 + 9) x 2 = 56


@pytest.mark.parametrize(
    ("joker", "baglam", "beklenen"),
    [
        ("j_joker", {}, 28 * 6),  # +4 mult
        ("j_greedy_joker", {}, 28 * 5),  # tek elmas: +3 mult
        ("j_lusty_joker", {}, 56),  # kupa yok
        ("j_wrathful_joker", {}, 28 * 5),  # tek maça
        ("j_gluttenous_joker", {}, 56),  # sinek yok
        ("j_jolly", {}, 28 * 10),  # Pair: +8 mult
        ("j_zany", {}, 56),  # Three of a Kind yok
        ("j_sly", {}, (28 + 50) * 2),  # Pair: +50 chips
        ("j_wily", {}, 56),
        ("j_half", {}, 28 * 22),  # 2 kart <= 3: +20 mult
        ("j_banner", {"kalan_discard": 3}, (28 + 90) * 2),  # discard başına +30 chips
        ("j_banner", {"kalan_discard": 0}, 56),
        ("j_mystic_summit", {"kalan_discard": 0}, 28 * 17),
        ("j_mystic_summit", {"kalan_discard": 1}, 56),
        ("j_blue_joker", {"deste_boyu": 20}, (28 + 40) * 2),  # kart başına +2 chips
        ("j_gros_michel", {}, 28 * 17),
        ("j_cavendish", {}, 28 * 6),  # x3
        ("j_duo", {}, 28 * 4),  # Pair: x2
        ("j_trio", {}, 56),
        ("j_acrobat", {"kalan_el": 0}, 28 * 6),  # son el: x3
        ("j_acrobat", {"kalan_el": 1}, 56),
        ("j_card_sharp", {"sayaclar": {"Pair": (0, 1)}}, 28 * 6),  # bu turda bu tür daha önce oynandı: x3
        ("j_card_sharp", {"sayaclar": {"Pair": (0, 0)}}, 56),
        ("j_supernova", {"sayaclar": {"Pair": (3, 1)}}, 28 * 6),  # önceki 3 + şimdiki = 4 mult
        ("j_supernova", {}, 28 * 3),  # ilk oynanış: +1 mult
    ],
)
def test_tek_joker_elle_hesaplanmis_skorlar(joker, baglam, beklenen):
    """Her joker için, oyundan okunan kurala göre elle hesaplanmış skoru motorun verdiğini doğrular."""
    assert skor(kartlar(*PAIR9), joker, **baglam) == beklenen


@pytest.mark.parametrize(
    ("el", "joker", "beklenen"),
    [
        (["S_K", "D_K"], "j_scary_face", (30 + 60) * 2),  # her yüz kartı +30 chips: taban 10+10+10, +60
        (["S_K", "D_K"], "j_smiley", 30 * 12),  # her yüz kartı +5 mult
        (["S_9", "D_9"], "j_scary_face", 56),  # yüz kartı yok
        (["S_8", "D_8"], "j_fibonacci", 26 * 18),  # 8'ler: +8 mult each
        (["S_8", "D_8"], "j_even_steven", 26 * 10),  # çift rütbe: +4 mult each
        (["S_9", "D_9"], "j_odd_todd", (28 + 62) * 2),  # tek rütbe: +31 chips each
        (["S_A", "D_A"], "j_odd_todd", (10 + 22 + 62) * 2),  # As da tek sayılır
        (["S_A", "D_A"], "j_scholar", (10 + 22 + 40) * 10),  # As: +20 chips +4 mult each
        (["S_4", "D_4"], "j_walkie_talkie", (10 + 8 + 20) * 10),  # 4 ve 10: +10 chips +4 mult each
        (["S_10", "D_10"] if False else ["S_T", "D_T"], "j_walkie_talkie", (10 + 20 + 20) * 10),
        (["S_9", "D_9"], "j_fibonacci", 56),  # 9 Fibonacci dizisinde değil
    ],
)
def test_kart_basina_jokerler(el, joker, beklenen):
    """Oynanan her puanlayan karta uygulanan jokerlerin (yüz kartı, rütbe, renk) doğru hesaplandığını doğrular."""
    assert skor(kartlar(*el), joker) == beklenen


def test_puanlamayan_kartlar_kart_basina_joker_tetiklemez():
    """Puanlamayan kartın (kicker) kart başına jokeri tetiklemediğini doğrular."""
    el = kartlar("S_9", "D_9", "H_8", "C_3", "S_2")  # çift 9, 8'ler kicker
    assert skor(el, "j_fibonacci") == (10 + 18) * 2 + 0 * 0  # 9'lar Fibonacci değil, 8/3/2 puanlamaz


def test_joker_sirasi_toplama_ve_carpma_icin_onemlidir():
    """+mult ve x mult jokerlerinin sırayla uygulandığını (sol önce) doğrular: sıra değişince sonuç değişir."""
    assert skor(kartlar(*PAIR9), "j_cavendish", "j_joker") == 28 * (2 * 3 + 4)
    assert skor(kartlar(*PAIR9), "j_joker", "j_cavendish") == 28 * ((2 + 4) * 3)


def test_abstract_joker_joker_sayisina_bagli():
    """Abstract Joker'in elde taşınan joker sayısı x3 mult verdiğini doğrular (gerçek oyunda 1 joker için +3 gözlendi)."""
    assert skor(kartlar(*PAIR9), "j_abstract") == 28 * 5
    assert skor(kartlar(*PAIR9), "j_abstract", "j_joker") == 28 * (2 + 6 + 4)


def test_joker_baskilari_foil_holo_polychrome():
    """Joker baskılarının sırasını (Foil chips ve Holo mult önce, Polychrome en sonda) doğrular."""
    el = kartlar(*PAIR9)
    assert puan_hesapla(el, jokerler=[Joker("j_joker", "foil")]).skor == (28 + 50) * 6
    assert puan_hesapla(el, jokerler=[Joker("j_joker", "holo")]).skor == 28 * (2 + 10 + 4)
    assert puan_hesapla(el, jokerler=[Joker("j_joker", "polychrome")]).skor == int(28 * ((2 + 4) * 1.5))
    assert puan_hesapla(el, jokerler=[Joker("j_joker", "negative")]).skor == 28 * 6  # negative yalnızca yuva verir


def test_misprint_belirsiz_isaretlenir_beklenen_degeri_kullanir():
    """Misprint'in rastgele olduğu için `belirsiz` işaretlendiğini ve beklenen değerle (11,5 mult) hesaplandığını doğrular."""
    r = puan_hesapla(kartlar(*PAIR9), jokerler=[Joker("j_misprint")])
    assert r.belirsiz is True and r.skor == int(28 * 13.5)


def test_el_tespitini_degistiren_jokerler_bayrak_olur():
    """Splash, Four Fingers ve Shortcut jokerlerinin el tespitini değiştirdiğini doğrular."""
    el = kartlar("S_9", "D_9", "H_2", "C_3", "D_5")
    assert puan_hesapla(el).skor == 56
    assert puan_hesapla(el, jokerler=[Joker("j_splash")]).skor == (10 + 28) * 2  # tüm kartlar puanlar
    assert puan_hesapla(kartlar("H_2", "H_5", "H_9", "H_J"), jokerler=[Joker("j_four_fingers")]).el_turu == "Flush"
    assert puan_hesapla(kartlar("H_2", "D_3", "S_5", "C_6", "H_7"), jokerler=[Joker("j_shortcut")]).el_turu == "Straight"


def test_desteklenmeyen_joker_bildirilir():
    """Etkisi tanımlı olmayan jokerlerin `bilinmeyenler` ile bildirildiğini doğrular."""
    j = [Joker("j_joker"), Joker("j_blueprint"), Joker("j_splash")]
    assert bilinmeyenler(j) == ["j_blueprint"] and desteklenen_mi(j[0]) and desteklenen_mi(j[2])


def test_apiden_joker_baskisini_okur():
    """Oyun kartındaki `modifier.edition` değerinden joker baskısının okunduğunu, bilinmeyen değerde hata verildiğini doğrular."""
    assert apiden({"key": "j_joker", "modifier": {"enhancement": "JOKER MULT"}}) == Joker("j_joker")
    assert apiden({"key": "j_joker", "modifier": {"edition": "FOIL"}}) == Joker("j_joker", "foil")
    with pytest.raises(ValueError):
        apiden({"key": "j_joker", "modifier": {"edition": "RAINBOW"}})


def test_iceren_tablosu_tam_motorun_el_tespitiyle_ayni():
    """`ICEREN` tablosunun, fazladan kart olmayan ellerde `degerlendir` sonucundaki içerilen türlerle aynı olduğunu doğrular."""
    from balatro_ai.sim.el_turu import degerlendir

    ornekler = {
        "High Card": ["S_A"], "Pair": ["S_9", "D_9"], "Two Pair": ["S_9", "D_9", "S_4", "D_4"],
        "Three of a Kind": ["S_9", "D_9", "H_9"], "Straight": ["S_5", "D_6", "H_7", "C_8", "S_9"],
        "Flush": ["H_2", "H_5", "H_9", "H_J", "H_K"], "Full House": ["S_5", "D_5", "H_5", "C_K", "D_K"],
        "Four of a Kind": ["S_J", "H_J", "C_J", "D_J"], "Straight Flush": ["S_5", "S_6", "S_7", "S_8", "S_9"],
        "Five of a Kind": ["S_A", "H_A", "D_A", "C_A", "S_A"], "Flush House": ["H_5", "H_5", "H_5", "H_K", "H_K"],
        "Flush Five": ["S_A"] * 5,
    }
    for tur, el in ornekler.items():
        d = degerlendir(kartlar(*el))
        assert d.el_turu == tur and set(d.iceren) == ICEREN[tur], tur


def test_hizli_yol_tam_motorla_ayni_rastgele_el_ve_jokerler():
    """Rastgele eller, rastgele joker kümeleri (baskılı da) ve bağlamlarla hızlı `en_iyi_oynanis` skorunun tam motorun en iyisiyle aynı olduğunu doğrular."""
    rng = random.Random(2026)
    deste = [f"{s}_{r}" for s in "SHCD" for r in "23456789TJQKA"]
    anahtarlar = [k for k in TANIMLAR if k != "j_misprint"]
    for _ in range(250):
        el = kartlar(*rng.sample(deste, rng.choice([6, 7, 8])))
        jokerler = [Joker(rng.choice(anahtarlar), rng.choice([None, None, "foil", "holo", "polychrome"])) for _ in range(rng.randint(1, 4))]
        sayaclar = {t: (rng.randint(0, 5), rng.randint(0, 2)) for t in EL_TABLOSU}
        baglam = Baglam(kalan_discard=rng.randint(0, 4), kalan_el=rng.randint(0, 3), deste_boyu=rng.randint(0, 44), sayaclar=sayaclar)
        hizli, idx = en_iyi_oynanis(el, VARSAYILAN, [k.chip for k in el], jokerler, baglam)
        en = 0
        for n in range(1, 6):
            for alt in itertools.combinations(range(len(el)), n):
                en = max(en, puan_hesapla([el[i] for i in alt], jokerler=jokerler, baglam=baglam).skor)
        assert hizli == en, ([f"{k.renk}{k.rutbe}" for k in el], [(j.key, j.baski) for j in jokerler])
        assert puan_hesapla([el[i] for i in idx], jokerler=jokerler, baglam=baglam).skor == hizli
