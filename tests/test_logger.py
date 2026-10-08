import json

import pytest

from balatro_ai.data.logger import LoggerHatasi, RunLogger, yapilandirma_ozeti
from balatro_ai.data.okuma import baglan

AJAN = {"tur": "random", "model_id": None}
CFG = {"rastgele_tohum": 1, "b": 2}


def _baslat(log, **kw):
    log.run_basla(
        seed="TEST0001", deste="RED", stake="WHITE", yaklasim="B_dar",
        ajan=AJAN, yapilandirma=CFG, oyun={"mod": "balatrobot 1.5.2"}, **kw,
    )


def _karar(log, **kw):
    return log.karar(
        faz="SELECTING_HAND", gozlem={"money": 4}, komut={"yontem": "play", "parametreler": {"cards": [0]}},
        ham_durum={"seed": "TEST0001", "money": 4}, sure_ms=1.5, **kw,
    )


def test_tam_run_kaydi_satirlari(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        assert _karar(log) == 1
        assert _karar(log, ek={"not": "x"}) == 2
        log.run_bitir(durum="kaybetti", son_ante=2, son_round=4, olum_nedeni="Big Blind")
    satirlar = [json.loads(s) for s in (tmp_path / "r1.jsonl").read_text().splitlines()]
    assert [s["tip"] for s in satirlar] == ["run_basi", "karar", "karar", "run_sonu"]
    assert satirlar[0]["sema"] == "sema_v1"
    assert satirlar[0]["yapilandirma_ozeti"] == yapilandirma_ozeti(CFG)
    assert satirlar[0]["surumler"]["kod"]
    assert [s["adim"] for s in satirlar[1:3]] == [1, 2]
    assert satirlar[3]["adim_sayisi"] == 2


def test_var_olan_run_dosyasi_degistirilemez(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.run_bitir(durum="iptal")
    with pytest.raises(LoggerHatasi), RunLogger(tmp_path, run_id="r1"):
        pass


def test_baslamadan_karar_yazilamaz(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log, pytest.raises(LoggerHatasi):
        _karar(log)


def test_bitis_sonrasi_yazilamaz(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.run_bitir(durum="kazandi")
        with pytest.raises(LoggerHatasi):
            _karar(log)


def test_istisna_olursa_run_sonu_hata_olarak_yazilir(tmp_path):
    with pytest.raises(RuntimeError), RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        _karar(log)
        raise RuntimeError("oyun coktu")
    son = json.loads((tmp_path / "r1.jsonl").read_text().splitlines()[-1])
    assert son["tip"] == "run_sonu" and son["durum"] == "hata" and "oyun coktu" in son["hata"]


def test_gecersiz_girdiler_reddedilir(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        with pytest.raises(LoggerHatasi):
            log.run_basla(seed=None, deste="RED", stake="WHITE", yaklasim="x", ajan={}, yapilandirma={})
        _baslat(log)
        with pytest.raises(LoggerHatasi):
            log.karar(faz="x", gozlem={}, komut={"parametreler": {}}, ham_durum={})
        with pytest.raises(LoggerHatasi):
            log.run_bitir(durum="belki")


def test_yapilandirma_ozeti_anahtar_sirasindan_bagimsiz():
    assert yapilandirma_ozeti({"a": 1, "b": 2}) == yapilandirma_ozeti({"b": 2, "a": 1})


def test_duckdb_ile_sorgulanir(tmp_path):
    for rid, durum, ante in (("r1", "kaybetti", 2), ("r2", "kazandi", 8)):
        with RunLogger(tmp_path, run_id=rid) as log:
            _baslat(log)
            _karar(log)
            _karar(log)
            log.run_bitir(durum=durum, son_ante=ante)
    with RunLogger(tmp_path, run_id="r3") as log:  # yarım kalmış: run_sonu yok
        _baslat(log)
        _karar(log)
        log._dosya.flush()
        con = baglan(tmp_path)
        assert con.execute("SELECT count(*) FROM runs").fetchone()[0] == 3
        assert con.execute("SELECT count(*) FROM decisions").fetchone()[0] == 5
        satir = con.execute("SELECT durum, son_ante FROM runs WHERE run_id='r2'").fetchone()
        assert satir == ("kazandi", 8)
        assert con.execute("SELECT durum FROM runs WHERE run_id='r3'").fetchone()[0] is None
        seed = con.execute(
            "SELECT json_extract_string(ham_durum,'$.seed') FROM decisions LIMIT 1"
        ).fetchone()[0]
        assert seed == "TEST0001"
        yontem = con.execute(
            "SELECT json_extract_string(komut,'$.yontem') FROM decisions LIMIT 1"
        ).fetchone()[0]
        assert yontem == "play"
