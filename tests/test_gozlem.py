"""İnsan gözlemi filtresinin testleri: seed, deste sırası ve yüzü kapalı kartların gizlenmesi."""

import json
import random
from pathlib import Path

from balatro_ai.env.gozlem import insan_gozlemi

DURUM = json.loads((Path(__file__).parent / "veri" / "durum_el_secimi.json").read_text())


def test_seed_gozlemde_yok_ama_ham_durumda_var():
    """Seed'in ham durumda bulunduğunu ama gözlemde bulunmadığını doğrular."""
    assert "seed" in DURUM
    assert "seed" not in insan_gozlemi(DURUM)


def test_ham_durum_degismez():
    """Filtrenin girdisi olan ham durumu değiştirmediğini doğrular."""
    once = json.dumps(DURUM, sort_keys=True)
    insan_gozlemi(DURUM)
    assert json.dumps(DURUM, sort_keys=True) == once


def test_deste_sirasi_gozlemi_etkilemez():
    # Aynı deste farklı çekiliş sıralarında aynı gözlemi vermeli: sıra bilgisi sızmamalı.
    """Aynı deste farklı çekiliş sıralarında aynı gözlemi verir; yani sıra bilgisi sızmaz."""
    for tohum in range(5):
        karisik = json.loads(json.dumps(DURUM))
        random.Random(tohum).shuffle(karisik["cards"]["cards"])
        assert insan_gozlemi(karisik) == insan_gozlemi(DURUM)


def test_deste_icerigi_korunur():
    """Destedeki kartların (hangileri kaldığı) gözlemde korunduğunu doğrular."""
    ham = sorted(k["key"] for k in DURUM["cards"]["cards"])
    assert [k["key"] for k in insan_gozlemi(DURUM)["cards"]["cards"]] == ham


def test_el_ve_diger_alanlar_aynen_kalir():
    """El, para ve faz gibi gizli olmayan alanların değişmediğini doğrular."""
    g = insan_gozlemi(DURUM)
    assert g["hand"] == DURUM["hand"]
    assert g["money"] == DURUM["money"]
    assert g["state"] == DURUM["state"]


def _kapali_el():
    """İkinci kartı yüzü kapalı işaretlenmiş bir el durumu üretir."""
    d = json.loads(json.dumps(DURUM))
    d["hand"]["cards"][1]["state"] = {"hidden": True}
    return d


def test_kapali_el_karti_kimligi_gizlenir():
    """Yüzü kapalı el kartının kimliğinin (rütbe, renk) gözlemden silindiğini doğrular."""
    ham = _kapali_el()
    kimlik = ham["hand"]["cards"][1]["key"]
    g = insan_gozlemi(ham)
    assert g["hand"]["cards"][1] == {"state": {"hidden": True}}
    assert kimlik not in json.dumps(g["hand"])


def test_acik_el_kartlari_ve_konumlari_degismez():
    """Açık el kartlarının ve konumlarının filtreden etkilenmediğini doğrular."""
    g = insan_gozlemi(_kapali_el())
    for i, kart in enumerate(DURUM["hand"]["cards"]):
        if i != 1:
            assert g["hand"]["cards"][i] == kart


def test_deste_kartlari_kapali_isaretli_olsa_da_korunur():
    """Deste kartları teknik olarak 'kapalı' işaretli olsa da kimliklerinin korunduğunu doğrular (deste ekranı görünür).
    """
    g = insan_gozlemi(DURUM)
    assert all("key" in k for k in g["cards"]["cards"])


def test_kapali_dukkan_ve_joker_de_gizlenir():
    """Yüzü kapalı joker ve mağaza kartlarının da gizlendiğini doğrular."""
    d = json.loads(json.dumps(DURUM))
    d["jokers"] = {"cards": [{"key": "j_joker", "state": {"hidden": True}}], "count": 1}
    d["shop"] = {"cards": [{"key": "j_blueprint", "state": {"hidden": True}}], "count": 1}
    g = insan_gozlemi(d)
    assert "j_joker" not in json.dumps(g) and "j_blueprint" not in json.dumps(g)
