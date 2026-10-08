"""Gezegen değerlendirmesi (sim/gezegen.py) ve greedy ajanın mağaza/paket kararlarının testleri."""

import random

from balatro_ai.agents.greedy import GreedyAjan
from balatro_ai.env import aksiyonlar
from balatro_ai.sim.gezegen import (
    GEZEGEN_EL,
    YAYGIN_GEZEGENLER,
    gezegen_degerleri,
    ornek_eller,
    paket_beklenen_degeri,
    yukselt,
)
from balatro_ai.sim.kartlar import anahtardan
from balatro_ai.sim.puan import EL_TABLOSU

TABLO = {t: (float(v[0]), float(v[1])) for t, v in EL_TABLOSU.items()}
DESTE = [anahtardan(f"{s}_{r}") for s in "SHCD" for r in "23456789TJQKA"]


def test_gezegenler_on_iki_el_turunu_kapsar():
    """Her el türünün tam bir gezegeni olduğunu doğrular."""
    assert sorted(GEZEGEN_EL.values()) == sorted(EL_TABLOSU)


def test_yukselt_bir_seviye_ekler_girdiyi_degistirmez():
    """Yükseltmenin oyunun seviye artışını (Pair: +15 chips, +1 mult) eklediğini ve girdiyi değiştirmediğini doğrular."""
    yeni = yukselt(TABLO, "Pair")
    assert yeni["Pair"] == (25.0, 3.0) and TABLO["Pair"] == (10.0, 2.0)
    assert yukselt(yeni, "Pair")["Pair"] == (40.0, 4.0)


def test_degerler_negatif_degil_ve_ayni_ornekle_tekrarlanir():
    """Gezegen değerlerinin negatif olmadığını ve aynı örneklerle aynı çıktığını doğrular."""
    eller = ornek_eller(DESTE, 150, random.Random(3))
    d1 = gezegen_degerleri(eller, TABLO, YAYGIN_GEZEGENLER)
    d2 = gezegen_degerleri(eller, TABLO, YAYGIN_GEZEGENLER)
    assert d1 == d2 and all(v >= 0 for v in d1.values())
    assert d1["c_mercury"] > 0 and d1["c_uranus"] > 0


def test_paket_beklenen_degeri_secenek_sayisiyla_artar():
    """Mega paketin (5 seçenek, 2 seçim) normal paketten (3 seçenek, 1 seçim) daha değerli olduğunu doğrular."""
    d = {g: float(i) for i, g in enumerate(YAYGIN_GEZEGENLER)}
    rng = random.Random(1)
    assert paket_beklenen_degeri(d, "mega", rng) > paket_beklenen_degeri(d, "jumbo", rng) > paket_beklenen_degeri(d, "normal", rng)


# --- ajanın mağaza kararları -------------------------------------------------------------------
def _kart(key, fiyat=3, set_="PLANET"):
    """Mağaza veya paket kartı sözlüğü üretir."""
    return {"key": key, "label": key, "set": set_, "cost": {"buy": fiyat, "sell": 1}, "modifier": [], "state": []}


def _magaza(dukkan=(), paketler=(), tuketilebilir=(), para=10):
    """Tam desteli bir mağaza durumu üretir."""
    deste = [{"key": f"{k.renk}_{k.rutbe}", "state": [], "modifier": []} for k in DESTE]
    return {
        "state": "SHOP", "money": para, "round": {"reroll_cost": 5},
        "cards": {"cards": deste},
        "hands": {t: {"chips": v[0], "mult": v[1]} for t, v in TABLO.items()},
        "shop": {"cards": list(dukkan)}, "vouchers": {"cards": []}, "packs": {"cards": list(paketler)},
        "jokers": {"cards": [], "limit": 5}, "consumables": {"cards": list(tuketilebilir), "limit": 2},
        "blinds": {"a": {"status": "UPCOMING", "type": "SMALL"}},
    }


def _karar(g, **ajan_ayari):
    """Ajanın bu mağaza durumunda seçtiği komutun adını ve parametrelerini döndürür."""
    ajan_ayari.setdefault("magaza", True)  # mağaza davranışı varsayılan olarak kapalıdır; bu testler açık ister
    ajan = GreedyAjan(1, **ajan_ayari)
    a = ajan.sec(g, {"gecerli_aksiyonlar": aksiyonlar.gecerli(g, "tam")})
    k = aksiyonlar.komut(a)
    return k["yontem"], k["parametreler"], ajan.son_aciklama


def test_degerli_gezegeni_satin_alir():
    """Karşılanabilir ve değerli bir gezegen mağazada varsa ajanın onu satın aldığını doğrular."""
    yontem, p, a = _karar(_magaza(dukkan=[_kart("c_mercury")]))
    assert (yontem, p) == ("buy", {"card": 0}) and a["karar"] == "satin_al:c_mercury"


def test_parasi_yetmeyen_gezegeni_almaz_mağazadan_cikar():
    """Parası yetmeyen gezegen için satın alma yapılmadığını, mağazadan çıkıldığını doğrular."""
    assert _karar(_magaza(dukkan=[_kart("c_mercury")], para=2))[0] == "next_round"


def test_gezegen_olmayan_teklifleri_almaz():
    """Jokerin henüz değerlendirilemediği için alınmadığını doğrular."""
    assert _karar(_magaza(dukkan=[_kart("j_joker", 4, "JOKER")]))[0] == "next_round"


def test_elde_gezegen_varsa_hemen_kullanir():
    """Tüketilebilir slotundaki gezegenin hemen kullanıldığını doğrular."""
    yontem, p, a = _karar(_magaza(tuketilebilir=[_kart("c_uranus")]))
    assert (yontem, p) == ("use", {"consumable": 0}) and a["karar"] == "gezegen_kullan"


def test_gezegen_paketini_satin_alir():
    """Karşılanabilir bir gezegen paketinin satın alındığını doğrular."""
    yontem, p, _ = _karar(_magaza(paketler=[_kart("p_celestial_normal_1", 4, "BOOSTER")]))
    assert (yontem, p) == ("buy", {"pack": 0})


def test_diger_paket_turlerini_almaz():
    """Gezegen olmayan paketlerin (arcana, buffoon) satın alınmadığını doğrular."""
    assert _karar(_magaza(paketler=[_kart("p_arcana_normal_1", 4, "BOOSTER")]))[0] == "next_round"


def test_magaza_kapaliysa_hicbir_sey_almaz():
    """`magaza=False` ile (v1 davranışı) planet olsa bile mağazadan çıkıldığını doğrular."""
    assert _karar(_magaza(dukkan=[_kart("c_mercury")]), magaza=False)[0] == "next_round"


def test_esik_yuksekse_almaz():
    """Satın alma eşiği çok yüksekse değerli gezegenin bile alınmadığını doğrular."""
    assert _karar(_magaza(dukkan=[_kart("c_mercury")]), gezegen_esik=10_000)[0] == "next_round"


def test_en_oranli_gezegeni_secer():
    """İki gezegen arasında puan/fiyat oranı yüksek olanın seçildiğini doğrular (Pluto yerine Uranus)."""
    g = _magaza(dukkan=[_kart("c_pluto"), _kart("c_uranus")])
    assert _karar(g)[1] == {"card": 1}


def test_acik_pakette_en_degerli_gezegeni_secer():
    """Açık gezegen paketinde en yüksek değerli gezegenin seçildiğini ve değerli yoksa atlandığını doğrular."""
    g = _magaza()
    g["state"] = "SMODS_BOOSTER_OPENED"
    g["hand"] = {"cards": []}
    g["pack"] = {"cards": [_kart("c_pluto"), _kart("c_uranus"), _kart("c_mercury")]}
    yontem, p, _ = _karar(g)
    assert (yontem, p) == ("pack", {"card": 1})
    g["pack"] = {"cards": [_kart("c_sun", 0, "TAROT")]}
    assert _karar(g)[1] == {"skip": True}
