"""Paketin kurulup sürümünün okunduğunu denetleyen duman testi."""

import balatro_ai


def test_paket_surumu_okunuyor():
    """Paket sürümünün okunabildiğini (kurulu olduğunu) doğrular."""
    assert balatro_ai.__version__ != "0.0.0+unknown"
