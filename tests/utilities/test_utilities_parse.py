# -*- coding: utf-8 -*-
"""Test ELM Ordinance retry utilities"""
from pathlib import Path

import pytest

from elm.utilities.parse import (
    clean_headers,
    combine_pages,
    is_double_col,
    format_html_tables,
    remove_blank_pages,
    replace_common_pdf_conversion_chars,
    replace_multi_dot_lines,
    remove_empty_lines_or_page_footers,
)

SAMPLE_TABLE_TEXT = """Some text.
<table>
    <tr>
        <th>Company</th>
        <th>Contact</th>
        <th>Country</th>
    </tr>
    <tr>
        <td>Alfreds Futterkiste</td>
        <td>Maria Anders</td>
        <td>Germany</td>
    </tr>
    <tr>
        <td>Centro comercial Moctezuma</td>
        <td>Francisco Chang</td>
        <td>Mexico</td>
    </tr>
</table>
"""
EXPECTED_TABLE_OUT = """Some text.
|    | Company                    | Contact         | Country   |
|---:|:---------------------------|:----------------|:----------|
|  0 | Alfreds Futterkiste        | Maria Anders    | Germany   |
|  1 | Centro comercial Moctezuma | Francisco Chang | Mexico    |
"""
PAGES_WITH_HEADERS_AND_FOOTERS = [
    "A title page",
    "Page 1.\n---\nOnce upon a time in a digital realm\n....\npp.1",
    "Page 2.\n---\nIn the vast expanse of ones and zeros\n....\npp.2",
    "Page 3.\n---\nA narrative unfolded, threads of code\n....\npp.3",
    "Page 4.\n---\nCharacters emerged, pixels on the screen\n....\npp.4",
    "Page 5.\n---\nPlot twists encoded, through algorithms\n....\npp.5",
    "Page 6.\n---\nWith each line, the story deepened\n....\npp.6",
    "Page 7.\n---\nSyntax and semantics entwined, crafting a tale\n....\npp.7",
    "Page 8.\n---\nIn the end, a digital landscape\n....\npp.8",
    "Page 9.\n---\nleaving imprints in the memory bytes\n....\npp.9",
    "",
]


def test_is_double_col():
    """Test the `is_double_col` heuristic function"""

    assert not is_double_col("Some Text")
    assert is_double_col("Some    Text")
    assert is_double_col(
        """
        Some double    here over
        column text    multiple lines.
        given          :)
        """
    )
    assert not is_double_col(
        """
        Some text  with odd   spacing
        and  multiple lines but  not
        double column!
        """
    )


def test_remove_blank_pages():
    """Test the `remove_blank_pages` function"""

    assert remove_blank_pages([]) == []
    assert remove_blank_pages([""]) == []
    assert remove_blank_pages(["Here", ""]) == ["Here"]
    assert remove_blank_pages(["We", "  "]) == ["We"]
    assert remove_blank_pages(["", " Go ", "  ", "Again"]) == [" Go ", "Again"]


def test_format_html_tables():
    """Test the `format_html_tables` function (basic execution)"""
    assert format_html_tables("test") == "test"
    assert format_html_tables(SAMPLE_TABLE_TEXT) == EXPECTED_TABLE_OUT

    bad_table_text = SAMPLE_TABLE_TEXT + "\nBad table:\n<table></table>"
    assert format_html_tables(bad_table_text) == bad_table_text


def test_clean_headers():
    """Test the `clean_headers` function (basic execution)"""
    out = combine_pages(clean_headers(PAGES_WITH_HEADERS_AND_FOOTERS))

    assert "A title page" in out
    assert len(out) > 100
    assert "---" not in out
    assert "...." not in out
    assert "Page" not in out
    assert "pp." not in out


def test_replace_common_pdf_conversion_chars():
    """Test the `replace_common_pdf_conversion_chars` function (basic exec.)"""

    out = replace_common_pdf_conversion_chars("Hello\r\n\x0cMy name is\r")
    assert out == "Hello\nMy name is\n"


def test_replace_multi_dot_lines():
    """Test the `replace_multi_dot_lines` function (basic exec.)"""

    assert replace_multi_dot_lines(".") == "."
    assert replace_multi_dot_lines("..") == ".."
    assert replace_multi_dot_lines("...") == "..."
    assert replace_multi_dot_lines("....") == "..."
    assert replace_multi_dot_lines(".....") == "..."
    assert replace_multi_dot_lines("......") == "..."
    assert replace_multi_dot_lines("......\n......") == "...\n..."


def test_remove_empty_lines_or_page_footers():
    """Test the `remove_empty_lines_or_page_footers` function (basic exec.)"""
    assert remove_empty_lines_or_page_footers("Hello\n   99\r!") == "Hello\n!"
    assert remove_empty_lines_or_page_footers("Hello\n   \r!") == "Hello\n!"
    assert remove_empty_lines_or_page_footers("\n\r") == "\n"

    keep_str = "Hello\n Some text  99\r!"
    assert remove_empty_lines_or_page_footers(keep_str) == keep_str

    multi_line_str = """
    10. To regulate and restrict the erection, construction, reconstruction,
    alteration, repair, and use of building, structures, and land.




                                                                         1
    CHAPTER 1.02 ORDINANCE PROVISIONS
    """

    expected_out = """
    10. To regulate and restrict the erection, construction, reconstruction,
    alteration, repair, and use of building, structures, and land.
    CHAPTER 1.02 ORDINANCE PROVISIONS
    """

    assert remove_empty_lines_or_page_footers(multi_line_str) == expected_out


if __name__ == "__main__":
    pytest.main(["-q", "--show-capture=all", Path(__file__), "-rapP"])
