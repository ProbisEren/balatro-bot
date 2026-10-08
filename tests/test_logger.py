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


def _durum_magaza():
    k = lambda key, fiyat: {"key": key, "label": key.upper(), "cost": {"buy": fiyat}}
    return {
        "money": 10,
        "shop": {"cards": [k("c_mercury", 3), k("j_juggler", 4)]},
        "vouchers": {"cards": [k("v_crystal_ball", 10)]},
        "packs": {"cards": [k("p_buffoon", 4), k("p_celestial", 6)]},
    }


def test_magazada_gorulen_ve_alinmayan_teklifler_sorgulanir(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(
            faz="SHOP", gozlem={}, ham_durum=_durum_magaza(),
            komut={"yontem": "buy", "parametreler": {"pack": 1}},
            cevap={"state": "SMODS_BOOSTER_OPENED"},
        )
        log.run_bitir(durum="iptal")
    con = baglan(tmp_path)
    satirlar = con.execute(
        "SELECT tur, anahtar, fiyat, alindi FROM shop_teklifleri ORDER BY tur, indeks"
    ).fetchall()
    assert len(satirlar) == 5  # 2 kart + 1 kupon + 2 paket
    alinanlar = [s[1] for s in satirlar if s[3]]
    assert alinanlar == ["p_celestial"]
    reddedilen = [s[1] for s in satirlar if not s[3]]
    assert set(reddedilen) == {"c_mercury", "j_juggler", "v_crystal_ball", "p_buffoon"}


def test_pakette_gorulen_ve_secilen_kartlar(tmp_path):
    kartlar = [{"key": f"c_{i}", "label": f"P{i}", "value": {"effect": "x"}} for i in range(5)]
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(
            faz="SMODS_BOOSTER_OPENED", gozlem={}, ham_durum={"pack": {"cards": kartlar}},
            komut={"yontem": "pack", "parametreler": {"card": 2}},
        )
        log.run_bitir(durum="iptal")
    satirlar = baglan(tmp_path).execute(
        "SELECT anahtar, secildi FROM paket_icerikleri ORDER BY indeks"
    ).fetchall()
    assert [s[0] for s in satirlar] == [f"c_{i}" for i in range(5)]
    assert [s[1] for s in satirlar] == [False, False, True, False, False]


def test_oynanan_eller_kartlariyla_ve_skor_degisimiyle(tmp_path):
    el = [{"key": k} for k in ("S_A", "D_J", "C_9", "D_9")]
    once = {"hand": {"cards": el}, "round": {"hands_left": 4, "discards_left": 3, "chips": 0}}
    sonra = {"round": {"chips": 56}}
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(
            faz="SELECTING_HAND", gozlem={}, ham_durum=once, cevap=sonra,
            komut={"yontem": "play", "parametreler": {"cards": [2, 3]}},
        )
        log.run_bitir(durum="iptal")
    satir = baglan(tmp_path).execute(
        "SELECT islem, kartlar, kalan_el, skor_once, skor_sonra FROM eller"
    ).fetchone()
    assert satir == ("play", ["C_9", "D_9"], 4, 0, 56)


def test_reddedilen_komut_hatasi_kaydedilir(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(
            faz="MENU", gozlem={}, ham_durum={}, cevap=None,
            komut={"yontem": "play", "parametreler": {"cards": [0]}},
            hata={"kod": -32002, "mesaj": "Invalid state"},
        )
        log.run_bitir(durum="iptal")
    satir = baglan(tmp_path).execute(
        "SELECT json_extract_string(hata, '$.kod') FROM decisions"
    ).fetchone()
    assert satir[0] == "-32002"


def _gercek_durum():
    from pathlib import Path

    return json.loads((Path(__file__).parent / "veri" / "durum_el_secimi.json").read_text())


def test_oynanan_elin_turu_ve_cekilen_kartlar_gercek_durumdan(tmp_path):
    once = _gercek_durum()
    el_idler = [k["id"] for k in once["hand"]["cards"]]
    # İndeks 2 ve 3 (C_9, D_9) oynanır: Pair. İki yeni kart gelir.
    sonra = json.loads(json.dumps(once))
    sonra["hands"]["Pair"]["played"] += 1
    sonra["round"]["chips"] = 56
    kalan = [k for i, k in enumerate(sonra["hand"]["cards"]) if i not in (2, 3)]
    yeni = [{"id": 9001, "key": "H_2"}, {"id": 9002, "key": "S_3"}]
    sonra["hand"]["cards"] = kalan + yeni
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(
            faz="SELECTING_HAND", gozlem={}, ham_durum=once, cevap=sonra,
            komut={"yontem": "play", "parametreler": {"cards": [2, 3]}},
        )
        log.run_bitir(durum="iptal")
    satir = baglan(tmp_path).execute(
        "SELECT kartlar, el_turu, cekilen, skor_once, skor_sonra, ante FROM eller"
    ).fetchone()
    assert satir[0] == ["C_9", "D_9"]
    assert satir[1] == "Pair"
    assert satir[2] == ["H_2", "S_3"]
    assert (satir[3], satir[4], satir[5]) == (0, 56, 1)
    assert len(el_idler) == 8


def test_discard_el_turu_bos_ve_cekilen_dolu(tmp_path):
    once = _gercek_durum()
    sonra = json.loads(json.dumps(once))
    sonra["hand"]["cards"] = sonra["hand"]["cards"][2:] + [{"id": 9001, "key": "H_2"}, {"id": 9002, "key": "S_3"}]
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(
            faz="SELECTING_HAND", gozlem={}, ham_durum=once, cevap=sonra,
            komut={"yontem": "discard", "parametreler": {"cards": [0, 1]}},
        )
        log.run_bitir(durum="iptal")
    satir = baglan(tmp_path).execute("SELECT islem, kartlar, el_turu, cekilen FROM eller").fetchone()
    assert satir[0] == "discard" and satir[1] == ["S_A", "D_J"]
    assert satir[2] is None and satir[3] == ["H_2", "S_3"]


def test_tuketilebilir_kullanimi_eldeki_ve_paketten(tmp_path):
    durum = {
        "hand": {"cards": [{"key": "S_A"}, {"key": "D_J"}, {"key": "C_9"}]},
        "consumables": {"cards": [{"key": "c_magician"}, {"key": "c_hermit"}]},
        "pack": {"cards": [{"key": "c_death"}, {"key": "c_strength"}]},
    }
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(faz="SELECTING_HAND", gozlem={}, ham_durum=durum,
                  komut={"yontem": "use", "parametreler": {"consumable": 0, "cards": [1, 2]}})
        log.karar(faz="SMODS_BOOSTER_OPENED", gozlem={}, ham_durum=durum,
                  komut={"yontem": "pack", "parametreler": {"card": 1, "targets": [0]}})
        log.karar(faz="SMODS_BOOSTER_OPENED", gozlem={}, ham_durum=durum,
                  komut={"yontem": "pack", "parametreler": {"skip": True}})
        log.run_bitir(durum="iptal")
    satirlar = baglan(tmp_path).execute(
        "SELECT kaynak, anahtar, hedef_kartlar FROM tuketilebilir_kullanimi ORDER BY adim"
    ).fetchall()
    assert satirlar == [("eldeki", "c_magician", ["D_J", "C_9"]), ("paket", "c_strength", ["S_A"])]


def test_satislar_joker_ve_tuketilebilir(tmp_path):
    durum = {
        "jokers": {"cards": [{"key": "j_joker", "cost": {"sell": 2}}]},
        "consumables": {"cards": [{"key": "c_fool", "cost": {"sell": 1}}]},
    }
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(faz="SHOP", gozlem={}, ham_durum=durum,
                  komut={"yontem": "sell", "parametreler": {"joker": 0}})
        log.karar(faz="SHOP", gozlem={}, ham_durum=durum,
                  komut={"yontem": "sell", "parametreler": {"consumable": 0}})
        log.run_bitir(durum="iptal")
    satirlar = baglan(tmp_path).execute(
        "SELECT tur, anahtar, satis_fiyati FROM satislar ORDER BY adim"
    ).fetchall()
    assert satirlar == [("joker", "j_joker", 2), ("tuketilebilir", "c_fool", 1)]


def test_elde_tutulan_kartlar_secilmeyenler(tmp_path):
    once = _gercek_durum()
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(faz="SELECTING_HAND", gozlem={}, ham_durum=once,
                  komut={"yontem": "play", "parametreler": {"cards": [2, 3]}})
        log.run_bitir(durum="iptal")
    tutulan = baglan(tmp_path).execute("SELECT tutulan FROM eller").fetchone()[0]
    assert tutulan == ["S_A", "D_J", "S_8", "H_8", "C_5", "C_4"]


def test_elde_tutulan_ve_kullanilan_tuketilebilirler(tmp_path):
    durum = {"consumables": {"cards": [
        {"key": "c_magician", "label": "Magician"}, {"key": "c_mercury", "label": "Mercury"}]}}
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(faz="SELECTING_HAND", gozlem={}, ham_durum=durum,
                  komut={"yontem": "use", "parametreler": {"consumable": 1}})
        log.karar(faz="SELECTING_HAND", gozlem={}, ham_durum=durum,
                  komut={"yontem": "play", "parametreler": {"cards": [0]}})
        log.run_bitir(durum="iptal")
    satirlar = baglan(tmp_path).execute(
        "SELECT adim, anahtar, kullanildi, satildi FROM eldeki_tuketilebilirler ORDER BY adim, indeks"
    ).fetchall()
    assert satirlar == [
        (1, "c_magician", False, False), (1, "c_mercury", True, False),
        (2, "c_magician", False, False), (2, "c_mercury", False, False),
    ]


def test_secenekler_kaydedilir_ve_sorgulanir(tmp_path):
    secenekler = [{"yontem": "play", "parametreler": {"cards": [i]}} for i in range(3)]
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(faz="SELECTING_HAND", gozlem={}, ham_durum={}, secenekler=secenekler,
                  komut=secenekler[1])
        log.run_bitir(durum="iptal")
    adet = baglan(tmp_path).execute(
        "SELECT json_array_length(secenekler) FROM decisions"
    ).fetchone()[0]
    assert adet == 3


# --- bütünlük alanları ---


def test_gozlemde_seed_varsa_kayit_reddedilir(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        with pytest.raises(LoggerHatasi, match="seed"):
            log.karar(faz="X", gozlem={"ic": {"seed": "ABC"}}, komut=None, ham_durum={})
        assert log._adim == 0  # hiçbir şey yazılmadı


def test_gozlemde_sirasiz_deste_reddedilir(tmp_path):
    deste = {"cards": {"cards": [{"key": "S_A", "id": 2}, {"key": "C_2", "id": 1}]}}
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        with pytest.raises(LoggerHatasi, match="sıralı değil"):
            log.karar(faz="X", gozlem=deste, komut=None, ham_durum={})


def test_gercek_filtrenin_ciktisi_korumadan_gecer_ham_durum_gecmez(tmp_path):
    from balatro_ai.env.gozlem import insan_gozlemi

    ham = _gercek_durum()
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(faz="SELECTING_HAND", gozlem=insan_gozlemi(ham), komut=None, ham_durum=ham)
        with pytest.raises(LoggerHatasi):
            log.karar(faz="SELECTING_HAND", gozlem=ham, komut=None, ham_durum=ham)


def test_hile_komutu_run_i_gecersiz_isaretler(tmp_path):
    with RunLogger(tmp_path, run_id="temiz") as log:
        _baslat(log)
        _karar(log)
        log.run_bitir(durum="kaybetti")
    with RunLogger(tmp_path, run_id="hileli") as log:
        _baslat(log)
        log.karar(faz="X", gozlem={}, ham_durum={}, komut={"yontem": "set", "parametreler": {"chips": 300}})
        log.karar(faz="X", gozlem={}, ham_durum={}, komut={"yontem": "set", "parametreler": {"money": 99}})
        log.run_bitir(durum="kazandi")
    con = baglan(tmp_path)
    satirlar = dict(con.execute("SELECT run_id, gecerli FROM runs").fetchall())
    assert satirlar == {"temiz": True, "hileli": False}
    ham = con.execute("SELECT manipule_komutlari FROM runs WHERE run_id='hileli'").fetchone()[0]
    assert json.loads(ham) == ["set"]


def test_yarim_kalan_run_gecerli_sayilmaz(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        _karar(log)
        log._dosya.flush()
        assert baglan(tmp_path).execute("SELECT gecerli FROM runs").fetchone()[0] is False


def test_seed_bolumu_zorunlu_ve_gecerli_degerler(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        with pytest.raises(LoggerHatasi, match="bölüm"):
            log.run_basla(seed="S", deste="RED", stake="WHITE", yaklasim="x", ajan=AJAN,
                          yapilandirma={}, bolum="rastgele")
        _baslat(log, bolum="test")
        log.run_bitir(durum="iptal")
    assert baglan(tmp_path).execute("SELECT bolum FROM runs").fetchone()[0] == "test"


def test_durum_ozetleri_ayni_durumda_ayni(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        _karar(log)
        _karar(log)
        log.run_bitir(durum="iptal")
    ozetler = baglan(tmp_path).execute("SELECT ham_durum_ozeti FROM decisions").fetchall()
    assert ozetler[0] == ozetler[1] and len(ozetler[0][0]) == 64


def test_sureler_ayri_kaydedilir(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        log.karar(faz="X", gozlem={}, ham_durum={}, komut=None, sure_ms=10.0, bot_ms=3.0, api_ms=7.0)
        log.run_bitir(durum="iptal")
    assert baglan(tmp_path).execute("SELECT sure_ms, bot_ms, api_ms FROM decisions").fetchone() == (10.0, 3.0, 7.0)


def test_sayaclar_ve_lovely_log_ozeti(tmp_path):
    lovely = tmp_path / "lovely.log"
    lovely.write_text("INFO - ok\nERROR - bir hata\nINFO - x\n ERROR bir daha\n")
    with RunLogger(tmp_path / "veri", run_id="r1") as log:
        _baslat(log, oyun_ayarlari={"fast": True}, profil_parmak_izi="abc")
        log.sayac_artir("zaman_asimi")
        log.sayac_artir("yeniden_deneme", 2)
        with pytest.raises(LoggerHatasi):
            log.sayac_artir("uydurma")
        log.run_bitir(durum="hata", lovely_log=lovely)
    con = baglan(tmp_path / "veri")
    sayaclar, lovely_ozet = con.execute("SELECT sayaclar, lovely_log FROM runs").fetchone()
    assert json.loads(sayaclar) == {"zaman_asimi": 1, "yeniden_deneme": 2, "oyun_cokmesi": 0, "mod_hatasi": 0}
    assert json.loads(lovely_ozet)["hata_satiri"] == 1  # yalnızca " ERROR " biçimli satır
    assert con.execute("SELECT profil_parmak_izi FROM runs").fetchone()[0] == "abc"


def test_json_null_sql_null_olur_hatasiz_komut_hata_degildir(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log)
        _karar(log)  # hata=None, cevap=None
        log.karar(faz="X", gozlem={}, ham_durum={}, komut={"yontem": "play", "parametreler": {}},
                  hata={"kod": -32002, "mesaj": "x"}, cevap={"state": "A"}, secenekler=[1])
        log.karar(faz="X", gozlem={}, ham_durum={}, komut=None)
        log.run_bitir(durum="iptal")
    con = baglan(tmp_path)
    assert con.execute("SELECT count(*) FROM decisions WHERE hata IS NOT NULL").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM decisions WHERE cevap IS NOT NULL").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM decisions WHERE komut IS NULL").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM decisions WHERE secenekler IS NOT NULL").fetchone()[0] == 1


def test_test_manipule_rolu_gecersiz_sayilir(tmp_path):
    with RunLogger(tmp_path, run_id="r1") as log:
        _baslat(log, rol="test_manipule")
        log.run_bitir(durum="iptal")
    assert baglan(tmp_path).execute("SELECT gecerli FROM runs").fetchone()[0] is False
