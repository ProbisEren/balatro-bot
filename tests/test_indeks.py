from balatro_ai.data.logger import RunLogger
from balatro_ai.data.okuma import baglan
from balatro_ai.eval.indeks import sonraki_deney_dizini, tablo, yaz


def _run(klasor, run_id, ajan="random", durum="kaybetti", ante=2):
    with RunLogger(klasor, run_id=run_id) as log:
        log.run_basla(seed="S", deste="RED", stake="WHITE", yaklasim="B_dar", ajan={"tur": ajan}, yapilandirma={})
        log.run_bitir(durum=durum, son_ante=ante)


def test_deney_klasorleri_sirayla_numaralanir(tmp_path):
    a = sonraki_deney_dizini(tmp_path, "greedy", "dar", "Deneme Bir")
    assert a.name == "01_greedy_dar_deneme-bir"
    a.mkdir()
    (tmp_path / "07_eski_dar_x").mkdir()
    assert sonraki_deney_dizini(tmp_path, "rastgele", "tam", "x").name == "08_rastgele_tam_x"
    # numarasız klasörler sayıyı bozmaz
    (tmp_path / "notlar").mkdir()
    assert sonraki_deney_dizini(tmp_path, "a", "b", "c").name.startswith("08_")


def test_indeks_tablosu_klasorlerden_kurulur(tmp_path):
    d1, d2 = tmp_path / "01_rastgele_dar_a", tmp_path / "02_greedy_dar_b"
    _run(d1, "r1", ante=1)
    _run(d1, "r2", ante=1)
    _run(d2, "r3", ajan="greedy", durum="kazandi", ante=8)
    metin = tablo(tmp_path)
    assert "| 01 | `01_rastgele_dar_a` | random | B_dar | 2 | 2 | 1.0 | 0 |" in metin
    assert "| 02 | `02_greedy_dar_b` | greedy | B_dar | 1 | 1 | 8.0 | 1 |" in metin
    assert yaz(tmp_path).read_text(encoding="utf-8") == metin


def test_runs_gorunumunde_sira_kolonu(tmp_path):
    for i, rid in enumerate(("a", "b", "c"), start=1):
        _run(tmp_path, f"2026010{i}-{rid}")
    sirali = baglan(tmp_path).execute("SELECT run_id, sira FROM runs ORDER BY sira").fetchall()
    assert [s[1] for s in sirali] == [1, 2, 3]
