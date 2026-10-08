from balatro_ai.agents.rastgele import RastgeleAjan
from balatro_ai.agents.rutbe_grubu import RutbeGrubuAjan, _secilecek_kartlar
from balatro_ai.env import aksiyonlar


def _el(*rutbeler):
    return [{"value": {"rank": r, "suit": "S"}} for r in rutbeler]


def test_en_buyuk_grup_secilir_cift_uc_iki_cift():
    assert _secilecek_kartlar(_el("A", "K", "9", "9", "2", "3", "4", "5")) == [2, 3]  # çift
    assert _secilecek_kartlar(_el("5", "5", "5", "K", "K", "2", "3", "4")) == [0, 1, 2, 3, 4]  # full house
    assert _secilecek_kartlar(_el("9", "9", "4", "4", "A", "K", "2", "3")) == [0, 1, 2, 3]  # iki çift


def test_cift_yoksa_en_yuksek_kart():
    assert _secilecek_kartlar(_el("2", "7", "K", "4", "9", "J", "3", "5")) == [2]


def test_ajan_sadece_gecerli_aksiyon_dondurur():
    bilgi = {"gecerli_aksiyonlar": [10, 20, 30]}
    gozlem = {"state": "SHOP", "hand": {"cards": []}}
    for ajan in (RastgeleAjan(1), RutbeGrubuAjan(1)):
        assert {ajan.sec(gozlem, bilgi) for _ in range(30)} <= {10, 20, 30}


def test_rutbe_ajani_hedef_aksiyon_gecerliyse_onu_secer():
    kartlar = _el("A", "K", "9", "9", "2", "3", "4", "5")
    hedef = aksiyonlar.KOMBINASYONLAR.index((2, 3))
    bilgi = {"gecerli_aksiyonlar": [hedef, 0, 1]}
    assert RutbeGrubuAjan(1).sec({"state": "SELECTING_HAND", "hand": {"cards": kartlar}}, bilgi) == hedef
