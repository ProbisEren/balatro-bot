"""Son-el denetim aracının (eval/denetim.py) testleri."""

from balatro_ai.data.logger import RunLogger
from balatro_ai.eval.denetim import son_el_ihlalleri


def _kayit(klasor, run_id, ek, sonraki):
    """Son elde, discard hakkı olan tek bir oynama kararı içeren run kaydı yazar."""
    with RunLogger(klasor, run_id=run_id) as log:
        log.run_basla(seed=run_id, deste="RED", stake="WHITE", yaklasim="x", ajan={"tur": "t"}, yapilandirma={})
        log.karar(
            faz="SELECTING_HAND", gozlem={},
            ham_durum={"round": {"hands_left": 1, "discards_left": 2, "chips": 0}},
            komut={"yontem": "play", "parametreler": {"cards": [0, 1]}},
            cevap={"state": sonraki}, ek={"ajan": ek},
        )
        log.run_bitir(durum="iptal")


def test_discard_daha_iyiyken_oynamak_ihlal_sayilir(tmp_path):
    """Ajanın kendi hesabında discard'ın kazanma olasılığı yüksekken oynadığı kararın ihlal olarak listelendiğini doğrular."""
    _kayit(tmp_path, "a", {"son_el_arama": {"oynayarak_kazanma": 0.0, "discard_ile_kazanma": 0.2}}, "GAME_OVER")
    ihlaller = son_el_ihlalleri(tmp_path)
    assert len(ihlaller) == 1 and ihlaller[0]["neden"] == "discard_daha_iyiydi"


def test_discard_daha_iyi_degilken_oynamak_ihlal_degil(tmp_path):
    """Oynamanın kazanma olasılığı discard'dan düşük olmadığında (veya şans hiç yokken) ihlal sayılmadığını doğrular."""
    _kayit(tmp_path / "x", "a", {"son_el_arama": {"oynayarak_kazanma": 1.0, "discard_ile_kazanma": 1.0}}, "ROUND_EVAL")
    _kayit(tmp_path / "y", "b", {"son_el_arama": {"oynayarak_kazanma": 0.0, "discard_ile_kazanma": 0.0}}, "GAME_OVER")
    assert son_el_ihlalleri(tmp_path / "x") == [] and son_el_ihlalleri(tmp_path / "y") == []


def test_arama_kaydi_yoksa_ve_kaybedildiyse_supheli(tmp_path):
    """Ajan son el aramasını yapmamış ve el kaybedilmişse (greedy v1 gibi) şüpheli olarak listelendiğini doğrular."""
    _kayit(tmp_path, "a", {}, "GAME_OVER")
    assert son_el_ihlalleri(tmp_path)[0]["neden"] == "arama_kaydi_yok_ve_kayip"
