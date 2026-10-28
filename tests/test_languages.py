from __future__ import annotations

from telovie.util.languages import (
    display_name,
    format_language_list,
    is_known,
    language_choices,
    normalize_code,
    parse_language_list,
)


def test_normalize_two_letter_codes():
    assert normalize_code("en") == "eng"
    assert normalize_code("HI") == "hin"
    assert normalize_code("ja") == "jpn"
    assert normalize_code("zh") == "chi"


def test_normalize_terminologic_aliases():
    assert normalize_code("deu") == "ger"
    assert normalize_code("fra") == "fre"
    assert normalize_code("zho") == "chi"
    assert normalize_code("ces") == "cze"
    assert normalize_code("nld") == "dut"
    assert normalize_code("ell") == "gre"


def test_normalize_ietf_and_junk():
    assert normalize_code("en-US") == "eng"
    assert normalize_code("pt_BR") == "por"
    assert normalize_code("  ") == ""
    assert normalize_code(None) == ""
    assert normalize_code("und") == "und"
    assert normalize_code("klingon") == "klingon"  # preserved, caller decides


def test_parse_list_preserves_order_and_dedupes():
    assert parse_language_list("en, jpn; en  hin") == ["eng", "jpn", "hin"]
    assert parse_language_list("") == []
    assert parse_language_list("und, eng") == ["eng"]


def test_format_list_canonicalises():
    assert format_language_list(["EN", "hi"]) == "eng,hin"
    assert format_language_list("en, en, ja") == "eng,jpn"
    assert format_language_list([]) == ""


def test_display_names_and_known():
    assert display_name("hin") == "Hindi"
    assert display_name("hi") == "Hindi"
    assert display_name("deu") == "German"
    assert display_name("xx") == "XX"
    assert is_known("eng") is True
    assert is_known("en") is True
    assert is_known("klingon") is False


def test_language_choices_sorted_by_name():
    choices = language_choices()
    assert ("eng", "English") in choices
    names = [name for _, name in choices]
    assert names == sorted(names)
