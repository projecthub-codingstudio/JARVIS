"""Tests for HWP structured XML parsing helpers."""
from __future__ import annotations

from jarvis.indexing.parsers import _build_hwp_text_elements, _parse_hwp_structured_xml_bytes


def test_build_hwp_text_elements_promotes_inline_headings() -> None:
    text = (
        "오프셋 자료형 의미 설명 0 hchar 특수 문자 코드 늘 31이다. "
        "그리기 개체 자료 구조 기본 구조 "
        "그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에 파일상에는 다음과 같은 구조로 저장된다."
    )

    elements = _build_hwp_text_elements(text)

    assert len(elements) == 1
    assert elements[0].metadata["heading_path"] == "그리기 개체 자료 구조 > 기본 구조"
    assert "파일상에는 다음과 같은 구조로 저장된다" in elements[0].text


def test_parse_hwp_structured_xml_bytes_extracts_heading_aware_text_and_table() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <HWPML>
      <BODY>
        <SECTION>
          <P><Text>그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에 파일상에는 다음과 같은 구조로 저장된다.</Text></P>
          <TableControl>
            <TableCaption><Text>표 76 그리기 개체 공통 속성</Text></TableCaption>
            <TableBody>
              <TableRow>
                <TableCell><Text>자료형</Text></TableCell>
                <TableCell><Text>설명</Text></TableCell>
              </TableRow>
              <TableRow>
                <TableCell><Text>BYTE stream</Text></TableCell>
                <TableCell><Text>개체 요소 속성</Text></TableCell>
              </TableRow>
            </TableBody>
          </TableControl>
        </SECTION>
      </BODY>
    </HWPML>
    """.encode("utf-8")

    elements = _parse_hwp_structured_xml_bytes(xml, path_name="fixture.hwp")

    text_elems = [e for e in elements if e.element_type == "text"]
    table_elems = [e for e in elements if e.element_type == "table"]

    assert len(text_elems) == 1
    assert text_elems[0].metadata["heading_path"] == "그리기 개체 자료 구조 > 기본 구조"
    assert len(table_elems) == 1
    assert table_elems[0].metadata["sheet_name"] == "표 76 그리기 개체 공통 속성"


def test_parse_hwp_structured_xml_bytes_propagates_recent_heading_to_following_text() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <HWPML>
      <BODY>
        <SECTION>
          <P><Text>그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있다.</Text></P>
          <P><Text>파일상에는 다음과 같은 구조로 저장된다.</Text></P>
        </SECTION>
      </BODY>
    </HWPML>
    """.encode("utf-8")

    elements = _parse_hwp_structured_xml_bytes(xml, path_name="fixture.hwp")

    text_elems = [e for e in elements if e.element_type == "text"]
    assert len(text_elems) == 2
    assert all(e.metadata["heading_path"] == "그리기 개체 자료 구조 > 기본 구조" for e in text_elems)
    assert "파일상에는 다음과 같은 구조로 저장된다." in text_elems[1].text


def test_parse_hwp_structured_xml_bytes_promotes_followup_heading_as_sibling() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <HWPML>
      <BODY>
        <SECTION>
          <P><Text>그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있다.</Text></P>
          <P><Text>저장되는 개체의 순서</Text></P>
          <P><Text>그리기 개체는 묶인 순서에 따라 계층 구조를 가진다.</Text></P>
        </SECTION>
      </BODY>
    </HWPML>
    """.encode("utf-8")

    elements = _parse_hwp_structured_xml_bytes(xml, path_name="fixture.hwp")

    text_elems = [e for e in elements if e.element_type == "text"]
    assert len(text_elems) == 2
    assert text_elems[0].metadata["heading_path"] == "그리기 개체 자료 구조 > 기본 구조"
    assert text_elems[1].metadata["heading_path"] == "그리기 개체 자료 구조 > 저장되는 개체의 순서"
    assert "계층 구조를 가진다." in text_elems[1].text


def test_parse_hwp_structured_xml_bytes_promotes_parent_then_subheading_sequence() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <HWPML>
      <BODY>
        <SECTION>
          <P><Text>그리기 개체 자료 구조</Text></P>
          <P><Text>기본 구조</Text></P>
          <P><Text>그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에 파일상에는 다음과 같은 구조로 저장된다.</Text></P>
        </SECTION>
      </BODY>
    </HWPML>
    """.encode("utf-8")

    elements = _parse_hwp_structured_xml_bytes(xml, path_name="fixture.hwp")

    text_elems = [e for e in elements if e.element_type == "text"]
    assert len(text_elems) == 1
    assert text_elems[0].metadata["heading_path"] == "그리기 개체 자료 구조 > 기본 구조"
    assert "파일상에는 다음과 같은 구조로 저장된다." in text_elems[0].text
