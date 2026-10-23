from linguapulse import text


def test_normalize_returns_nfc_form():
    decomposed = "xi\u030c"
    assert text.normalize(decomposed) == "x\u01d0"
    assert text.normalize(decomposed) != decomposed


def test_char_width_reports_the_columns_of_one_character():
    assert text.char_width("a") == 1
    assert text.char_width("你") == 2
    assert text.char_width("\u0301") == 0
    assert text.char_width(text.PDI) == 0


def test_display_width_counts_latin_and_arabic_as_one_column():
    assert text.display_width("hello") == 5
    assert text.display_width("مرحبا") == 5


def test_display_width_counts_chinese_as_two_columns():
    assert text.display_width("你好") == 4
    assert text.display_width("，") == 2


def test_display_width_ignores_combining_marks():
    assert text.display_width("é") == 1
    assert text.display_width("e\u0301") == 1


def test_display_width_ignores_directional_isolates():
    assert text.display_width(text.isolate("مرحبا")) == 5


def test_pad_uses_display_width_not_character_count():
    assert text.pad("你好", 6) == "你好  "
    assert text.pad("ab", 4) == "ab  "
    assert text.pad("ab", 4, align="right") == "  ab"


def test_pad_centers_the_text_in_the_gap():
    assert text.pad("ab", 6, align="center") == "  ab  "


def test_pad_keeps_text_that_is_wider_than_the_width():
    assert text.pad("你好", 2) == "你好"


def test_contains_rtl_detects_right_to_left_scripts():
    assert text.contains_rtl("مرحبا") is True
    assert text.contains_rtl("hello") is False
    assert text.contains_rtl("nǐ hǎo") is False


def test_isolate_wraps_only_right_to_left_text():
    assert text.isolate("hello") == "hello"
    assert text.isolate("مرحبا") == "⁧مرحبا⁩"


def test_strip_isolates_removes_every_marker():
    assert text.strip_isolates("⁦a⁧b⁨c⁩") == "abc"
