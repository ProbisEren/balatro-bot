import pytest

from balatro_ai.agents.greedy import GreedyAjan
from balatro_ai.data.okuma import baglan
from balatro_ai.env import aksiyonlar
from balatro_ai.env.ortam import BalatroOrtami
from balatro_ai.eval.calistir import run_oyna
from balatro_ai.sim.puan import EL_TABLOSU
from tests.sahte_oyun import SahteOyun


def _kart(key):
    return {"key": key, "state": [], "modifier": []}


def gozlem(el, deste=(), *, hedef=300, skor=0, hands_left=4, discards_left=3, boss=None):
    tur = "BOSS" if boss else "SMALL"
    return {
        "state": "SELECTING_HAND",
        "hand": {"cards": [_kart(k) for k in el]},
        "cards": {"cards": sorted((_kart(k) for k in deste), key=lambda c: c["key"])},
        "hands": {t: {"chips": v[0], "mult": v[1]} for t, v in EL_TABLOSU.items()},
        "blinds": {"small": {"status": "CURRENT", "type": tur, "name": boss or "Small Blind", "score": hedef}},
        "round": {"chips": skor, "hands_left": hands_left, "discards_left": discards_left},
        "jokers": {"cards": []},
    }


def bilgi(g, kume="dar"):
    ids = aksiyonlar.gecerli({**g, "money": 4}, kume)
    return {"gecerli_aksiyonlar": ids}


def coz(a):
    k = aksiyonlar.komut(a)
    return k["yontem"], tuple(k["parametreler"]["cards"])


def test_blind_biten_oynanis_varsa_onu_oynar():
    el = ["H_2", "H_5", "H_9", "H_J", "H_K", "D_3", "C_4", "S_7"]  # Flush = 284
    g = gozlem(el, deste=["S_A"], hedef=250)
    ajan = GreedyAjan(1)
    yontem, kartlar = coz(ajan.sec(g, bilgi(g)))
    assert (yontem, kartlar) == ("play", (0, 1, 2, 3, 4))
    assert ajan.son_aciklama["karar"] == "oyna_blind_biter" and ajan.son_aciklama["tahmin_skor"] == 284


def test_en_yuksek_skorlu_kombinasyonu_secer_discard_yoksa():
    el = ["S_A", "D_A", "H_9", "C_4", "S_2", "D_7", "H_K", "C_3"]
    g = gozlem(el, deste=["S_5"], hedef=1000, discards_left=0)
    ajan = GreedyAjan(1)
    yontem, kartlar = coz(ajan.sec(g, bilgi(g)))
    assert (yontem, kartlar) == ("play", (0, 1))  # A çifti: (10+22)*2 = 64, başka bir şey yok
    assert ajan.son_aciklama["karar"] == "oyna_discard_yok"


def test_secilen_oynanis_tum_kombinasyonlar_icinde_en_iyisidir():
    import itertools

    from balatro_ai.sim.kartlar import apiden
    from balatro_ai.sim.puan import puan_hesapla

    el = ["S_A", "D_A", "H_9", "C_9", "S_2", "D_7", "H_7", "C_3"]
    g = gozlem(el, hedef=10_000, discards_left=0)
    yontem, kartlar = coz(GreedyAjan(1).sec(g, bilgi(g)))
    kartlar_obj = [apiden(_kart(k)) for k in el]
    en = max(
        puan_hesapla([kartlar_obj[i] for i in c]).skor
        for n in range(1, 6) for c in itertools.combinations(range(8), n)
    )
    assert yontem == "play"
    assert puan_hesapla([kartlar_obj[i] for i in kartlar]).skor == en


def test_flush_cizerken_digerlerini_atar():
    el = ["S_A", "S_K", "S_Q", "S_J", "H_2", "D_3", "C_4", "D_5"]
    deste = [f"S_{r}" for r in "3456789T"] + ["H_6", "D_7", "C_8", "H_9"]
    g = gozlem(el, deste, hedef=2000)
    ajan = GreedyAjan(1)
    yontem, kartlar = coz(ajan.sec(g, bilgi(g)))
    assert yontem == "discard" and ajan.son_aciklama["karar"] == "discard"
    assert set(kartlar) <= {4, 5, 6, 7}  # maçaları tutar


def test_son_elde_gecme_ihtimali_varsa_discard_eder_yoksa_oynar():
    el = ["S_A", "S_K", "S_Q", "S_J", "H_2", "D_3", "C_4", "D_5"]
    deste = [f"S_{r}" for r in "3456789T"]
    g = gozlem(el, deste, hedef=500, hands_left=1)
    yontem, _ = coz(GreedyAjan(1).sec(g, bilgi(g)))
    assert yontem == "discard"  # akış/flush ihtimali var, mevcut en iyi 500'ün altında
    # Hiçbir çekiliş blind'ı geçirmiyorsa oynar.
    g2 = gozlem(el, deste, hedef=10**7, hands_left=1)
    yontem2, _ = coz(GreedyAjan(1).sec(g2, bilgi(g2)))
    assert yontem2 == "play"


def test_ayni_tohum_ayni_karar():
    el = ["S_A", "S_K", "S_Q", "S_J", "H_2", "D_3", "C_4", "D_5"]
    deste = [f"S_{r}" for r in "3456789T"] + ["H_6", "D_7"]
    g = gozlem(el, deste, hedef=2000)
    assert GreedyAjan(5).sec(g, bilgi(g)) == GreedyAjan(5).sec(g, bilgi(g))


def test_psychic_bossunda_bes_kart_oynar():
    el = ["S_A", "D_A", "H_9", "C_4", "S_2", "D_7", "H_K", "C_3"]
    g = gozlem(el, hedef=10_000, discards_left=0, boss="The Psychic")
    yontem, kartlar = coz(GreedyAjan(1).sec(g, bilgi(g)))
    assert yontem == "play" and len(kartlar) == 5  # 5'ten azı sıfır puan


def test_el_disindaki_asamalar_sabit_kural():
    ajan = GreedyAjan(1)
    for faz, beklenen in (("BLIND_SELECT", "select"), ("SHOP", "next_round")):
        g = {"state": faz, "money": 4, "blinds": {"a": {"status": "SELECT", "type": "SMALL"}},
             "shop": {"cards": []}, "vouchers": {"cards": []}, "packs": {"cards": []},
             "jokers": {"cards": [], "limit": 5}, "consumables": {"cards": [], "limit": 2}, "round": {"reroll_cost": 5}}
        ids = aksiyonlar.gecerli(g, "tam")
        assert aksiyonlar.komut(ajan.sec(g, {"gecerli_aksiyonlar": ids}))["yontem"] == beklenen
    g = {"state": "SMODS_BOOSTER_OPENED", "hand": {"cards": []}, "pack": {"cards": [{"key": "c_x"}]}}
    ids = aksiyonlar.gecerli(g, "tam")
    k = aksiyonlar.komut(ajan.sec(g, {"gecerli_aksiyonlar": ids}))
    assert k["yontem"] == "pack" and k["parametreler"].get("skip") is True


@pytest.mark.parametrize("kume", ["dar", "tam"])
def test_sahte_oyunda_greedy_run_bitirir_ve_karar_aciklamasi_loglanir(tmp_path, kume):
    env = BalatroOrtami(SahteOyun(), kume=kume, log_kok=tmp_path, uyku_sn=0, yerlesme_sn=0)
    ozet = run_oyna(env, GreedyAjan(3), "GRD0001")
    env.close()
    assert ozet["adim"] > 0
    con = baglan(tmp_path)
    assert con.execute("SELECT durum, gecerli FROM runs").fetchone()[1] is True
    kararlar = con.execute(
        "SELECT json_extract_string(ek, '$.ajan.karar') FROM decisions "
        "WHERE json_extract_string(ek, '$.ajan.karar') IS NOT NULL"
    ).fetchall()
    assert kararlar  # oynanan her el kararının açıklaması kayıtta
