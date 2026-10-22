from unittest import mock

from webserver.handlers import mynexus


def test_normalize_context_keeps_valid_fields():
    raw = {
        "reading": {
            "book_title": "长安十二时辰",
            "chapter_title": "第三章 巳正",
            "chapter_href": "text/ch03.xhtml",
            "section_index": 3,
            "progress_fraction": 0.421,
            "page": 118,
            "cfi": "epubcfi(/6/26!/4/2/2[c03])",
        },
        "selection": {"text": "长安一片月", "page": 118, "chapter_title": "第三章 巳正"},
    }
    out = mynexus._normalize_context(raw)
    assert out["reading"]["chapter_title"] == "第三章 巳正"
    assert out["reading"]["section_index"] == 3
    assert out["reading"]["progress_fraction"] == 0.421
    assert out["selection"]["text"] == "长安一片月"


def test_normalize_context_drops_malformed_fields():
    out = mynexus._normalize_context(
        {
            "reading": {"book_title": 123, "section_index": True, "progress_fraction": "x"},
            "selection": {"text": None},
        }
    )
    assert out["reading"]["book_title"] == ""
    assert out["reading"]["section_index"] == 0
    assert out["reading"]["progress_fraction"] == 0.0
    assert "selection" not in out


def test_normalize_context_rejects_non_dict():
    assert mynexus._normalize_context(None) is None
    assert mynexus._normalize_context([]) is None
    assert mynexus._normalize_context({}) is None
    assert mynexus._normalize_context({"reading": "x", "selection": 1}) is None


def test_normalize_context_clamps_fraction_and_truncates():
    out = mynexus._normalize_context(
        {
            "reading": {"progress_fraction": 1.7, "chapter_title": "题" * 300},
            "selection": {"text": "字" * 5000},
        }
    )
    assert out["reading"]["progress_fraction"] == 1.0
    assert len(out["reading"]["chapter_title"]) == mynexus._MAX_TITLE_CHARS
    assert len(out["selection"]["text"]) == mynexus._MAX_SELECTION_CHARS

    negative = mynexus._normalize_context({"reading": {"progress_fraction": -2}})
    assert negative["reading"]["progress_fraction"] == 0.0


def test_normalize_context_drops_selection_when_too_large():
    raw = {
        "reading": {"chapter_title": "第三章"},
        "selection": {"text": "字" * mynexus._MAX_SELECTION_CHARS},
    }
    with mock.patch.object(mynexus, "_MAX_CONTEXT_BYTES", 300):
        out = mynexus._normalize_context(raw)
    assert "selection" not in out
    assert out["reading"]["chapter_title"] == "第三章"


def test_normalize_context_none_when_reading_also_too_large():
    with mock.patch.object(mynexus, "_MAX_CONTEXT_BYTES", 10):
        assert mynexus._normalize_context({"reading": {"chapter_title": "第三章"}}) is None
