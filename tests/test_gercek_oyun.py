"""Çalışan Balatro + BalatroBot gerektirir. Oyun kapalıysa testler atlanır."""

import pytest

from balatro_ai.env.client import BaglantiHatasi, BalatroIstemci, GecersizDurum

istemci = BalatroIstemci(zaman_asimi=5)


def _oyun_acik() -> bool:
    try:
        return istemci.saglik()
    except BaglantiHatasi:
        return False


pytestmark = pytest.mark.skipif(not _oyun_acik(), reason="Balatro + BalatroBot çalışmıyor")


def test_saglik():
    assert istemci.saglik() is True


def test_durum_beklenen_alanlari_iceriyor():
    d = istemci.durum()
    for alan in ("state", "deck", "stake", "money", "ante_num", "round_num", "hands"):
        assert alan in d


def test_menuden_el_oynamak_gecersiz_durum_hatasi_verir():
    if istemci.durum()["state"] != "MENU":
        pytest.skip("Oyun ana menüde değil")
    with pytest.raises(GecersizDurum):
        istemci.oyna([0])
