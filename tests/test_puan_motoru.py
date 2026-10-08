"""Puan motorunun testleri: el tespiti, skor hesabı, boss etkileri ve gerçek oyun kayıtlarıyla doğrulama."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from balatro_ai.sim.el_turu import degerlendir
from balatro_ai.sim.kartlar import Kart, anahtardan, apiden
from balatro_ai.sim.puan import EL_TABLOSU, puan_hesapla, seviyeden


def el(*anahtarlar, **kw):
    """Oyun anahtarlarından (ör. 'S_A') düz kart listesi oluşturur."""
    return [anahtardan(a, **kw) for a in anahtarlar]


# --- el türü tespiti ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("kartlar", "tur", "puanlayan"),
    [
        (["S_A", "D_A", "H_9", "C_4", "S_2"], "Pair", (0, 1)),
        (["H_9", "D_9", "S_4", "C_4", "H_A"], "Two Pair", (0, 1, 2, 3)),
        (["S_T", "D_T", "H_T", "C_6", "H_5"], "Three of a Kind", (0, 1, 2)),
        (["H_5", "D_5", "S_5", "C_K", "D_K"], "Full House", (0, 1, 2, 3, 4)),
        (["S_J", "H_J", "C_J", "D_J", "C_3"], "Four of a Kind", (0, 1, 2, 3)),
        (["H_2", "H_5", "H_9", "H_J", "H_K"], "Flush", (0, 1, 2, 3, 4)),
        (["H_A", "D_2", "S_3", "C_4", "H_5"], "Straight", (0, 1, 2, 3, 4)),  # As düşük
        (["S_T", "D_J", "S_Q", "C_K", "H_A"], "Straight", (0, 1, 2, 3, 4)),  # As yüksek
        (["S_T", "S_J", "S_Q", "S_K", "S_A"], "Straight Flush", (0, 1, 2, 3, 4)),
        (["H_Q", "D_K", "S_A", "C_2", "H_3"], "High Card", (2,)),  # köşe sarma yok
        (["S_A", "H_A", "D_A", "C_A", "S_A"], "Five of a Kind", (0, 1, 2, 3, 4)),
        (["S_A", "S_A", "S_A", "S_A", "S_A"], "Flush Five", (0, 1, 2, 3, 4)),
        (["H_5", "H_5", "H_5", "H_K", "H_K"], "Flush House", (0, 1, 2, 3, 4)),
        (["C_8"], "High Card", (0,)),
        (["S_K", "D_K"], "Pair", (0, 1)),
    ],
)
def test_el_turu_ve_puanlayan_kartlar(kartlar, tur, puanlayan):
    """Çeşitli ellerde el türünün ve puanlayan kartların beklenen olduğunu doğrular."""
    d = degerlendir(el(*kartlar))
    assert (d.el_turu, d.puanlayan) == (tur, puanlayan)


def test_dort_kartla_flush_veya_straight_olmaz_dort_parmak_ile_olur():
    """4 kartlı flush ve straight'in yalnızca Four Fingers ile geçerli olduğunu doğrular."""
    flush4 = el("H_2", "H_5", "H_9", "H_J")
    assert degerlendir(flush4).el_turu == "High Card"
    assert degerlendir(flush4, dort_parmak=True).el_turu == "Flush"
    straight4 = el("H_5", "D_6", "S_7", "C_8")
    assert degerlendir(straight4).el_turu == "High Card"
    assert degerlendir(straight4, dort_parmak=True).el_turu == "Straight"


def test_kisayol_bir_rutbe_atlatir():
    """Shortcut ile bir rütbe atlayan straight'in geçerli olduğunu doğrular."""
    assert degerlendir(el("H_2", "D_3", "S_5", "C_6", "H_7")).el_turu == "High Card"
    assert degerlendir(el("H_2", "D_3", "S_5", "C_6", "H_7"), kisayol=True).el_turu == "Straight"


def test_wild_kart_her_rengi_sayar_stone_hicbirini():
    """Wild kartın her rengi, Stone kartın hiçbir rengi saymadığını doğrular."""
    wild = [anahtardan(k) for k in ("S_2", "S_5", "S_9", "S_J")] + [anahtardan("H_K", gelistirme="wild")]
    assert degerlendir(wild).el_turu == "Flush"
    tas = [anahtardan(k) for k in ("S_2", "S_5", "S_9", "S_J")] + [anahtardan("H_K", gelistirme="stone")]
    assert degerlendir(tas).el_turu == "High Card"


def test_stone_kart_en_yuksek_kart_secilmez():
    """High Card seçiminde Stone kartın seçilmediğini doğrular."""
    kartlar = [anahtardan("S_2"), anahtardan("S_J"), anahtardan("H_A", gelistirme="stone")]
    d = degerlendir(kartlar)
    assert d.el_turu == "High Card" and d.puanlayan == (1, 2)  # J puanlar, Stone zaten puanlar


def test_stone_kart_her_zaman_puanlar_rutbesi_yoktur():
    """Stone kartın her zaman puanladığını ama rütbesinin olmadığını doğrular."""
    kartlar = [anahtardan("S_9"), anahtardan("D_9"), anahtardan("H_2", gelistirme="stone")]
    d = degerlendir(kartlar)
    assert d.el_turu == "Pair" and d.puanlayan == (0, 1, 2)


def test_splash_butun_kartlari_puanlatir():
    """Splash ile oynanan tüm kartların puanladığını doğrular."""
    d = degerlendir(el("S_9", "D_9", "H_2", "C_3", "D_5"), splash=True)
    assert d.puanlayan == (0, 1, 2, 3, 4)


def test_iceren_turler():
    """Four of a Kind'ın Three of a Kind, Pair ve High Card'ı da içerdiğini doğrular."""
    d = degerlendir(el("S_J", "H_J", "C_J", "D_J", "C_3"))
    assert {"Four of a Kind", "Three of a Kind", "Pair", "High Card"} <= d.iceren


def test_gecersiz_kart_sayisi():
    """0 veya 6 kart oynamanın hata verdiğini doğrular."""
    with pytest.raises(ValueError):
        degerlendir([])
    with pytest.raises(ValueError):
        degerlendir(el("S_2", "S_3", "S_4", "S_5", "S_6", "S_7"))


# --- puan hesabı -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("kartlar", "skor"),
    [
        (["D_A", "S_Q", "H_Q", "D_5", "S_4"], 60),  # gerçek oyunda gözlendi
        (["S_9", "D_9", "H_2", "C_3", "D_5"], 56),
        (["H_2", "H_5", "H_9", "H_J", "H_K"], 284),
        (["H_A", "D_2", "S_3", "C_4", "H_5"], 220),
        (["S_T", "S_J", "S_Q", "S_K", "S_A"], 1208),
        (["H_Q", "D_K", "S_A", "C_2", "H_3"], 16),
        (["H_5", "D_5", "S_5", "C_K", "D_K"], 300),
        (["H_9", "D_9", "S_4", "C_4", "H_A"], 92),
        (["S_T", "D_T", "H_T", "C_6", "H_5"], 180),
        (["S_J", "H_J", "C_J", "D_J", "C_3"], 700),  # 3 puanlamaz
        (["S_A", "H_A", "D_A", "C_A", "S_A"], 2100),
        (["S_A", "S_A", "S_A", "S_A", "S_A"], 3440),
        (["H_5", "H_5", "H_5", "H_K", "H_K"], 2450),
        (["C_8"], 13),
    ],
)
def test_temel_skorlar(kartlar, skor):
    """Her el türü için elle hesaplanmış skorların motorla aynı olduğunu doğrular."""
    assert puan_hesapla(el(*kartlar)).skor == skor


def test_seviye_artisi_tablodan():
    """El seviyesi artışının oyunun tablosundan doğru hesaplandığını doğrular."""
    assert seviyeden("Pair", 1) == (10, 2)
    assert seviyeden("Pair", 3) == (40, 4)
    assert seviyeden("Flush", 2) == (50, 6)
    r = puan_hesapla(el("S_9", "D_9", "H_2", "C_3", "D_5"), seviyeler={"Pair": 3})
    assert r.skor == (40 + 18) * 4


def test_oyunun_verdigi_guncel_el_degerleri_kullanilir():
    """Oyun durumundaki güncel (chips, mult) değerlerinin kullanıldığını doğrular."""
    r = puan_hesapla(el("S_9", "D_9"), el_degerleri={"Pair": (25, 3)})
    assert r.skor == (25 + 18) * 3


def _cift(**kart_ozellik):
    """9-9 çifti, ilk 9'a özellik verilir. Taban: (10 + 9 + 9) x 2 = 56."""
    return [anahtardan("S_9", **kart_ozellik), anahtardan("D_9"), anahtardan("H_2"), anahtardan("C_3"), anahtardan("D_5")]


@pytest.mark.parametrize(
    ("ozellik", "skor"),
    [
        ({"gelistirme": "bonus"}, (10 + 9 + 9 + 30) * 2),
        ({"gelistirme": "mult"}, 28 * 6),
        ({"gelistirme": "glass"}, 28 * 4),
        ({"baski": "foil"}, (28 + 50) * 2),
        ({"baski": "holo"}, 28 * 12),
        ({"baski": "polychrome"}, 28 * 3),
        ({"gelistirme": "glass", "baski": "polychrome"}, 28 * 6),
        ({"muhur": "red"}, (28 + 9) * 2),  # kart iki kez tetiklenir
        ({"debuff": True}, (10 + 9) * 2),
        ({"kalici_chip": 5}, (28 + 5) * 2),
    ],
)
def test_kart_efektleri(ozellik, skor):
    """Bonus, mult, glass, baskı, kırmızı mühür, debuff ve kalıcı chip efektlerinin skoru doğru değiştirdiğini doğrular.
    """
    assert puan_hesapla(_cift(**ozellik)).skor == skor


def test_kirmizi_muhurlu_foil_iki_kez_tetiklenir():
    """Kırmızı mühürlü Foil kartın iki kez tetiklendiğini doğrular."""
    r = puan_hesapla(_cift(muhur="red", baski="foil"))
    assert r.skor == (10 + 9 + 9 + 9 + 100) * 2


def test_elde_kalan_steel_mult_carpar_cezasiz_olanlar_etkilemez():
    """Elde kalan Steel kartın mult'u 1,5 ile çarptığını, debuff'lı veya başka kartların etkilemediğini doğrular.
    """
    kartlar = _cift()
    steel = [anahtardan("S_A", gelistirme="steel"), anahtardan("H_K", gelistirme="steel")]
    assert puan_hesapla(kartlar, steel).skor == int(28 * (2 * 1.5 * 1.5))
    assert puan_hesapla(kartlar, [anahtardan("S_A", gelistirme="steel", debuff=True)]).skor == 56
    assert puan_hesapla(kartlar, [anahtardan("S_A", gelistirme="mult")]).skor == 56


def test_stone_kart_50_chip_ekler():
    """Stone kartın 50 chip eklediğini doğrular."""
    kartlar = [anahtardan("S_9"), anahtardan("D_9"), anahtardan("H_2", gelistirme="stone")]
    assert puan_hesapla(kartlar).skor == (10 + 9 + 9 + 50) * 2


def test_lucky_kart_belirsiz_isaretler():
    """Lucky kartın sonucu `belirsiz` işaretlediğini ve etkisini saymadığını doğrular."""
    r = puan_hesapla(_cift(gelistirme="lucky"))
    assert r.belirsiz is True and r.skor == 56


def test_skor_asagi_yuvarlanir():
    """Skorun chips x mult'un tam sayıya aşağı yuvarlanmışı olduğunu doğrular."""
    r = puan_hesapla([Kart("J", "S", baski="foil")] , [])
    assert r.chips == 5 + 10 + 50 and r.skor == 65
    r = puan_hesapla([Kart("J", "S", baski="polychrome")])
    assert (r.chips, r.mult, r.skor) == (15, 1.5, 22)


def test_etkisi_tanimli_olmayan_joker_hata_verir():
    """Oyundan okunup tanımlanmamış bir jokerle skor hesaplamanın sessizce yanlış sonuç vermek yerine hata verdiğini doğrular."""
    from balatro_ai.sim.jokerler import Joker

    with pytest.raises(NotImplementedError, match="j_blueprint"):
        puan_hesapla(_cift(), jokerler=[Joker("j_blueprint")])


def test_adim_kaydi():
    """Adım kaydı açıkken taban ve kart adımlarının kaydedildiğini doğrular."""
    r = puan_hesapla(_cift(), adim_kaydi=True)
    assert r.adimlar[0][0].startswith("taban") and len(r.adimlar) == 4  # taban, 2 kart, jokerler


# --- boss etkileri -----------------------------------------------------------------------------
def test_psychic_bes_kartten_azini_sifirlar():
    """The Psychic'te 5'ten az kartın 0 puan, 5 kartın normal puan verdiğini doğrular."""
    assert puan_hesapla(_cift()[:2], boss="The Psychic").skor == 0
    assert puan_hesapla(_cift(), boss="The Psychic").skor == 56


def test_renk_bossu_o_rengi_debuff_eder_wild_dahil():
    """Renk boss'larının o rengi (Wild dahil) debuff'ladığını doğrular."""
    kartlar = [anahtardan("C_9"), anahtardan("D_9")]
    assert puan_hesapla(kartlar, boss="The Club").skor == (10 + 9) * 2
    assert puan_hesapla(kartlar, boss="The Window").skor == (10 + 9) * 2
    assert puan_hesapla(kartlar, boss="The Goad").skor == 56  # maça yok
    wild = [anahtardan("H_9", gelistirme="wild"), anahtardan("D_9")]
    assert puan_hesapla(wild, boss="The Club").skor == (10 + 9) * 2


def test_plant_yuz_kartlarini_verdant_leaf_hepsini_debuff_eder():
    """The Plant'ın yüz kartlarını, Verdant Leaf'in tüm kartları debuff'ladığını doğrular."""
    kartlar = [anahtardan("S_K"), anahtardan("D_K")]
    assert puan_hesapla(kartlar, boss="The Plant").skor == 10 * 2
    assert puan_hesapla(_cift(), boss="Verdant Leaf").skor == 10 * 2


def test_flint_taban_degerleri_yariya_indirir():
    """The Flint'in taban chips ve mult'u yarıya indirdiğini doğrular."""
    assert puan_hesapla(_cift(), boss="The Flint").skor == (5 + 18) * 1


def test_arm_seviye_1_dusurur():
    """The Arm'ın seviyesi 1'den büyük eli bir seviye düşürdüğünü, seviye 1'de etkisiz olduğunu doğrular.
    """
    r = puan_hesapla(el("S_9", "D_9"), el_degerleri={"Pair": (25, 3)}, boss="The Arm")
    assert r.skor == (10 + 18) * 2
    r = puan_hesapla(el("S_9", "D_9"), el_degerleri={"Pair": (10, 2)}, boss="The Arm")  # seviye 1: etkisiz
    assert r.skor == (10 + 18) * 2


def test_eye_ve_mouth_el_turu_kurallari():
    """The Eye ve The Mouth'un el türü kurallarını doğrular."""
    assert puan_hesapla(_cift(), boss="The Eye", gecmis_turler=frozenset({"Pair"})).skor == 0
    assert puan_hesapla(_cift(), boss="The Eye", gecmis_turler=frozenset({"Flush"})).skor == 56
    assert puan_hesapla(_cift(), boss="The Mouth", ilk_tur="High Card").skor == 0
    assert puan_hesapla(_cift(), boss="The Mouth", ilk_tur="Pair").skor == 56


# --- kart çevirici -----------------------------------------------------------------------------
def test_apiden_gercek_oyundaki_bonus_kart_bicimi():
    k = apiden({"key": "C_2", "modifier": {"enhancement": "BONUS"}, "state": []})
    assert k == Kart("2", "C", gelistirme="bonus") and k.chip == 32


def test_apiden_debuff_bayragi_ve_bilinmeyen_deger():
    """Oyun kartındaki debuff bayrağının okunduğunu ve bilinmeyen geliştirme değerinde hata verildiğini doğrular.
    """
    assert apiden({"key": "S_5", "modifier": [], "state": {"debuff": True}}).debuff is True
    with pytest.raises(ValueError):
        apiden({"key": "S_5", "modifier": {"enhancement": "HAND UPGRADE"}, "state": []})


def test_tablo_oyunun_seviye_1_degerleriyle_ayni():
    """El tablosunun oyunun seviye 1 değerleriyle aynı olduğunu doğrular."""
    gercek = {
        "Flush Five": (160, 16), "Flush House": (140, 14), "Five of a Kind": (120, 12),
        "Straight Flush": (100, 8), "Four of a Kind": (60, 7), "Full House": (40, 4), "Flush": (35, 4),
        "Straight": (30, 4), "Three of a Kind": (30, 3), "Two Pair": (20, 2), "Pair": (10, 2), "High Card": (5, 1),
    }
    assert {t: (v[0], v[1]) for t, v in EL_TABLOSU.items()} == gercek


# --- gerçek oyun kayıtlarıyla doğrulama ----------------------------------------------------------
GERCEK = json.loads((Path(__file__).parent / "veri" / "gercek_eller.json").read_text())
VARSAYILAN = {t: (v[0], v[1]) for t, v in EL_TABLOSU.items()}


def _gercek_kartlar(e):
    """Gerçek oyun örneğindeki oynanan ve elde kalan kartları Kart nesnelerine çevirir."""
    oy = [apiden({"key": k, "state": s, "modifier": m}) for k, s, m in zip(e["oynanan"], e["oynanan_durum"], e["oynanan_modifier"], strict=True)]
    elde = [apiden({"key": k, "state": s, "modifier": {}}) for k, s in zip(e["elde"], e["elde_durum"], strict=True)]
    return oy, elde


def _el_degerleri(e):
    """Gerçek oyun örneği için el türlerinin (chips, mult) değerlerini kurar (seviye farkları dahil).
    """
    d = {t: (v[0], v[1]) for t, v in VARSAYILAN.items()}
    d.update({t: tuple(v) for t, v in e["seviye_farki"].items()})
    return d


def test_gercek_el_sayisi_yeterli():
    """Doğrulama verisinin yeterince el ve boss eli içerdiğini, jokerli ellerin az olduğunu doğrular.
    """
    assert len(GERCEK) >= 500
    assert sum(1 for e in GERCEK if e["blind"] == "BOSS") >= 50
    assert sum(1 for e in GERCEK if e["jokerler"]) < 20  # jokerli eller doğrulamadan çıkarıldı


@pytest.mark.parametrize("kural_modu", ["api_bayragi", "yalniz_boss_kurali"])
def test_motor_gercek_oyunun_verdigi_skorla_birebir_ayni(kural_modu):
    """Jokersiz gerçek ellerde motorun el türü ve skorunun oyunun verdiğiyle birebir aynı olduğunu doğrular (API debuff bayraklarıyla ve yalnızca boss kurallarıyla).
    """
    yanlis = []
    sayac = 0
    for e in GERCEK:
        if e["jokerler"]:
            continue
        oy, elde = _gercek_kartlar(e)
        if kural_modu == "yalniz_boss_kurali":  # API'nin debuff bayraklarını yok say, kuralları kullan
            oy = [replace(k, debuff=False) for k in oy]
            elde = [replace(k, debuff=False) for k in elde]
        boss = e["blind_adi"] if e["blind"] == "BOSS" else None
        r = puan_hesapla(oy, elde, el_degerleri=_el_degerleri(e), boss=boss)
        sayac += 1
        if (r.el_turu, r.skor) != (e["beklenen_tur"], e["beklenen_skor"]):
            yanlis.append((e["oynanan"], e["blind_adi"], e["beklenen_tur"], e["beklenen_skor"], r.el_turu, r.skor))
    assert sayac >= 500
    assert not yanlis, yanlis[:5]
