import json
import random
from pathlib import Path

from balatro_ai.env.gozlem import insan_gozlemi

DURUM = json.loads((Path(__file__).parent / "veri" / "durum_el_secimi.json").read_text())


def test_seed_gozlemde_yok_ama_ham_durumda_var():
    assert "seed" in DURUM
    assert "seed" not in insan_gozlemi(DURUM)


def test_ham_durum_degismez():
    once = json.dumps(DURUM, sort_keys=True)
    insan_gozlemi(DURUM)
    assert json.dumps(DURUM, sort_keys=True) == once


def test_deste_sirasi_gozlemi_etkilemez():
    # Aynı deste farklı çekiliş sıralarında aynı gözlemi vermeli: sıra bilgisi sızmamalı.
    for tohum in range(5):
        karisik = json.loads(json.dumps(DURUM))
        random.Random(tohum).shuffle(karisik["cards"]["cards"])
        assert insan_gozlemi(karisik) == insan_gozlemi(DURUM)


def test_deste_icerigi_korunur():
    ham = sorted(k["key"] for k in DURUM["cards"]["cards"])
    assert [k["key"] for k in insan_gozlemi(DURUM)["cards"]["cards"]] == ham


def test_el_ve_diger_alanlar_aynen_kalir():
    g = insan_gozlemi(DURUM)
    assert g["hand"] == DURUM["hand"]
    assert g["money"] == DURUM["money"]
    assert g["state"] == DURUM["state"]
