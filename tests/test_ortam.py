import json

import numpy as np
import pytest

from balatro_ai.agents.rastgele import RastgeleAjan
from balatro_ai.data.okuma import baglan
from balatro_ai.env import aksiyonlar
from balatro_ai.env.ortam import BalatroOrtami, GecersizAksiyon
from balatro_ai.eval.calistir import run_oyna
from tests.sahte_oyun import SahteOyun


def _ortam(kume="dar", log_kok=None, **kw):
    kw.setdefault("yerlesme_sn", 0)
    return BalatroOrtami(SahteOyun(), kume=kume, log_kok=log_kok, uyku_sn=0, **kw)


def _oyna_id(*indeksler):
    return aksiyonlar.KOMBINASYONLAR.index(tuple(indeksler))


def test_reset_dar_kume_el_secimine_gelir_ve_seed_gizli():
    env = _ortam()
    gozlem, _ = env.reset(options={"oyun_seed": "ABC"})
    assert gozlem["state"] == "SELECTING_HAND" and "seed" not in gozlem
    assert env.action_space.n == aksiyonlar.TOPLAM_DAR


def test_dar_kume_maske_8_kart_icin_436_aksiyon():
    # 8 kartın 1-5'li seçimleri: 8+28+56+70+56 = 218; oyna + discard = 436.
    env = _ortam()
    _, bilgi = env.reset(options={"oyun_seed": "ABC"})
    assert bilgi["action_mask"].sum() == 436
    assert len(bilgi["gecerli_aksiyonlar"]) == 436


def test_blind_gecilince_odul_1_ve_otomatik_magaza_gecisi():
    env = _ortam()
    env.reset(options={"oyun_seed": "ABC"})
    # 5 kart oyna: 100 chips = Small Blind hedefi -> +1; dar kümede otomatik cash_out/next_round/select.
    _, odul, bitti, _, bilgi = env.step(_oyna_id(0, 1, 2, 3, 4))
    assert odul == 1.0 and not bitti
    assert bilgi["faz"] == "SELECTING_HAND"  # sıradaki blind (Big) otomatik seçildi
    assert env.istemci.durum()["round_num"] == 1


def test_gecersiz_aksiyon_reddedilir():
    env = _ortam()
    env.reset(options={"oyun_seed": "ABC"})
    with pytest.raises(GecersizAksiyon):
        env.step(aksiyonlar._BLIND_SEC)  # dar kümede bu aksiyon hiç geçerli değil


def test_oyunun_reddettigi_aksiyon_engellenir_ve_durum_degismez():
    env = _ortam()
    env.reset(options={"oyun_seed": "ABC"})
    env.istemci.zorla_red = {"discard"}
    aksiyon = aksiyonlar.K + _oyna_id(0)
    _, odul, bitti, _, bilgi = env.step(aksiyon)
    assert bilgi["gecersiz"] and odul == 0.0 and not bitti
    assert not bilgi["action_mask"][aksiyon]
    assert bilgi["action_mask"].sum() == 435


def test_random_ajan_dar_kume_run_bitirir_ve_loglar(tmp_path):
    env = _ortam(log_kok=tmp_path, ajan=RastgeleAjan(1).bilgi(), yaklasim="B_dar")
    ozet = run_oyna(env, RastgeleAjan(1), "TEST0001")
    env.close()
    assert ozet["adim"] > 0
    con = baglan(tmp_path)
    run = con.execute("SELECT durum, gecerli, bolum, yaklasim, seed FROM runs").fetchone()
    assert run[0] in ("kazandi", "kaybetti") and run[1] is True
    assert run[3] == "B_dar" and run[4] == "TEST0001"
    # Her komut kaydedildi: botun kararları + otomatik geçişler.
    otomatik = con.execute(
        "SELECT count(*) FROM decisions WHERE json_extract_string(ek, '$.otomatik') = 'true'"
    ).fetchone()[0]
    toplam = con.execute("SELECT count(*) FROM decisions").fetchone()[0]
    assert 0 < otomatik < toplam
    # Gözlemde seed yok (logger de zaten reddederdi); ham durumda var.
    assert con.execute(
        "SELECT count(*) FROM decisions WHERE json_extract_string(gozlem, '$.seed') IS NOT NULL"
    ).fetchone()[0] == 0
    assert con.execute(
        "SELECT count(*) FROM decisions WHERE json_extract_string(ham_durum, '$.seed') = 'TEST0001'"
    ).fetchone()[0] > 0


def test_ayni_seed_ayni_ajan_ayni_run(tmp_path):
    sonuclar = []
    for ad in ("a", "b"):
        env = _ortam(log_kok=tmp_path / ad)
        sonuclar.append(run_oyna(env, RastgeleAjan(7), "TEST0001"))
        env.close()
    o = [{k: v for k, v in s.items() if k != "run_id"} for s in sonuclar]
    assert o[0] == o[1]
    ozet = [
        baglan(tmp_path / ad).execute("SELECT list(ham_durum_ozeti ORDER BY adim) FROM decisions").fetchone()[0]
        for ad in ("a", "b")
    ]
    assert ozet[0] == ozet[1]  # her adımın ham durumu bire bir aynı: determinizm


def test_tam_kume_magaza_ve_paket_kararlari_loglanir(tmp_path):
    env = _ortam(kume="tam", log_kok=tmp_path, yaklasim="A_tam")
    for tohum in range(8):  # farklı tohumlarla birkaç run: mağaza ve paket yollarını gez
        run_oyna(env, RastgeleAjan(tohum), f"TEST{tohum:04d}")
    env.close()
    con = baglan(tmp_path)
    assert con.execute("SELECT count(*) FROM shop_teklifleri").fetchone()[0] > 0
    assert con.execute("SELECT count(*) FROM runs WHERE gecerli").fetchone()[0] == 8
    yontemler = {
        r[0] for r in con.execute(
            "SELECT DISTINCT json_extract_string(komut, '$.yontem') FROM decisions"
        ).fetchall()
    }
    assert {"select", "play", "buy", "next_round"} <= yontemler


def test_max_adim_run_i_keser(tmp_path):
    env = _ortam(log_kok=tmp_path, max_adim=3)
    env.reset(options={"oyun_seed": "X"})
    kesildi = False
    for _ in range(3):
        # discard'a basmak run'ı bitirmez, adım sayısı dolar
        _, _, _, kesildi, _ = env.step(aksiyonlar.K + _oyna_id(0))
    assert kesildi
    env.close()
    assert baglan(tmp_path).execute("SELECT durum FROM runs").fetchone()[0] == "iptal"


def test_gozlem_filtresi_ortamdan_gecerek_gelir():
    env = _ortam()
    gozlem, _ = env.reset(options={"oyun_seed": "ABC"})
    anahtarlar = [k["key"] for k in gozlem["cards"]["cards"]]
    assert anahtarlar == sorted(anahtarlar)  # deste sırası ile çekiliş sırası ayrılmış
    assert isinstance(json.dumps(gozlem), str) and np.isscalar(gozlem["money"])


def test_atlama_sonrasi_gecikmeli_paket_beklenir():
    # Gerçek oyunda görülen kilitlenme: tag'in açtığı paket gecikmeyle gelir, ajan beklemeden devam ederse oyun takılır.
    env = _ortam(kume="tam", yerlesme_sn=0.4, yerlesme_en_cok_sn=3.0)
    env.istemci.skip_sonrasi_gecikmeli_paket = True
    _, bilgi = env.reset(options={"oyun_seed": "ABC"})
    assert bilgi["faz"] == "BLIND_SELECT"
    _, _, _, _, bilgi = env.step(aksiyonlar._BLIND_ATLA)
    assert bilgi["faz"] == "SMODS_BOOSTER_OPENED"  # ortam durum yerleşene kadar bekledi
    assert aksiyonlar._PAKET_ATLA in bilgi["gecerli_aksiyonlar"]


def _pakete_gir(env):
    env.istemci.skip_sonrasi_gecikmeli_paket = True
    env.reset(options={"oyun_seed": "ABC"})
    _, _, _, _, bilgi = env.step(aksiyonlar._BLIND_ATLA)
    assert bilgi["faz"] == "SMODS_BOOSTER_OPENED"
    return bilgi


def test_hedef_sayisi_reddedilen_mesajdan_ogrenilir():
    env = _ortam(kume="tam", yerlesme_sn=0.4, yerlesme_en_cok_sn=3.0)
    env.istemci.hedef_gerekir = {"c_arcana0": (1, 2)}
    _pakete_gir(env)
    # Hedef sayısı henüz bilinmiyor: hedefsiz seçim sunulur, oyun reddeder.
    _, _, _, _, bilgi = env.step(aksiyonlar._PAKET_SEC + 0)
    assert bilgi["gecersiz"]
    assert env._hedef_gereksinimi == {"c_arcana0": (1, 2)}
    ids = bilgi["gecerli_aksiyonlar"]
    assert aksiyonlar._PAKET_SEC + 0 not in ids  # artık hedefsiz sunulmaz
    hedefli = [i for i in ids if aksiyonlar._PAKET_HEDEFLI <= i < aksiyonlar._PAKET_HEDEFLI + aksiyonlar.H]
    assert hedefli and all(1 <= len(aksiyonlar.HEDEF_KOMBI[i - aksiyonlar._PAKET_HEDEFLI]) <= 2 for i in hedefli)
    assert max(aksiyonlar.HEDEF_KOMBI[i - aksiyonlar._PAKET_HEDEFLI][-1] for i in hedefli) < 8  # el 8 kart
    # Hedefli seçim kabul edilir.
    _, _, _, _, bilgi = env.step(hedefli[0])
    assert not bilgi["gecersiz"] and bilgi["faz"] != "SMODS_BOOSTER_OPENED"


def test_cevap_gelmeyen_pack_komutu_durum_degistiyse_basarili_sayilir(tmp_path):
    env = _ortam(kume="tam", log_kok=tmp_path, yerlesme_sn=0.4, yerlesme_en_cok_sn=3.0)
    env.istemci.pack_cevapsiz = True
    _pakete_gir(env)
    _, _, _, _, bilgi = env.step(aksiyonlar._PAKET_ATLA)
    assert not bilgi["gecersiz"] and bilgi["faz"] == "BLIND_SELECT"
    env.close()
    ek = baglan(tmp_path).execute(
        "SELECT json_extract_string(ek, '$.cevap_zaman_asimi') FROM decisions "
        "WHERE json_extract_string(komut, '$.yontem') = 'pack'"
    ).fetchone()[0]
    assert ek == "true"


@pytest.mark.parametrize(
    ("mesaj", "beklenen"),
    [
        ("Card 'c_sun' requires 1-3 target card(s). Provided: 0", ("c_sun", (1, 3))),
        ("Card 'c_death' requires exactly 2 target card(s). Provided: 0", ("c_death", (2, 2))),
        ("Card 'c_lovers' requires exactly 1 target card(s). Provided: 0", ("c_lovers", (1, 1))),
    ],
)
def test_hedef_hata_mesaji_bicimleri(mesaj, beklenen):
    env = _ortam(kume="tam")
    env._hedef_ogren(mesaj)
    assert env._hedef_gereksinimi == {beklenen[0]: beklenen[1]}
