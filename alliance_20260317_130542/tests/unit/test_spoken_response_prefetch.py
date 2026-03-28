from __future__ import annotations

from pathlib import Path

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.spoken_response_prefetch import predict_prefetchable_spoken_response


def _build_test_db(tmp_path: Path) -> Path:
    data_dir = tmp_path / "menubar-data"
    config = JarvisConfig(data_dir=data_dir)
    connection = init_database(config)
    try:
        connection.execute(
            "INSERT INTO documents (document_id, path, indexing_status, access_status)"
            " VALUES (?, ?, 'INDEXED', 'ACCESSIBLE')",
            ("diet-doc", "/kb/14day_diet_supplements_final.xlsx"),
        )
        connection.execute(
            "INSERT INTO chunks (chunk_id, document_id, text, heading_path)"
            " VALUES (?, ?, ?, ?)",
            (
                "diet-row-9",
                "diet-doc",
                "[Diet+Supplements_14days] Day=9 | Breakfast=구운계란2+요거트+베리 | Lunch=닭가슴살+현미밥1/2 | Dinner=순두부+김+피망",
                "table-row-Diet+Supplements_14days-9",
            ),
        )
        connection.execute(
            "INSERT INTO documents (document_id, path, indexing_status, access_status)"
            " VALUES (?, ?, 'INDEXED', 'ACCESSIBLE')",
            ("other-doc", "/kb/project_schedule.xlsx"),
        )
        connection.execute(
            "INSERT INTO chunks (chunk_id, document_id, text, heading_path)"
            " VALUES (?, ?, ?, ?)",
            (
                "other-row-9",
                "other-doc",
                "[SprintPlan] Day=9 | Breakfast=스탠드업 | Lunch=스프린트 리뷰 | Dinner=회고",
                "table-row-SprintPlan-9",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return data_dir


def test_predict_prefetchable_spoken_response_prefers_diet_table_rows(tmp_path: Path) -> None:
    data_dir = _build_test_db(tmp_path)

    predicted = predict_prefetchable_spoken_response(
        "안녕하세요 다이어트 식단표 에서 9일 회차 아침 메뉴 알려 주세요",
        data_dir=data_dir,
    )

    assert predicted == "9일차 아침은 구운계란 두 개와 요거트와 베리입니다."


def test_predict_prefetchable_spoken_response_skips_non_prefetchable_queries(tmp_path: Path) -> None:
    data_dir = _build_test_db(tmp_path)

    predicted = predict_prefetchable_spoken_response(
        "pipeline.py 구조 설명해줘",
        data_dir=data_dir,
    )

    assert predicted == ""


def test_predict_prefetchable_spoken_response_preserves_day_meal_pairs(tmp_path: Path) -> None:
    data_dir = _build_test_db(tmp_path)
    config = JarvisConfig(data_dir=data_dir)
    connection = init_database(config)
    try:
        connection.execute(
            "INSERT INTO documents (document_id, path, indexing_status, access_status)"
            " VALUES (?, ?, 'INDEXED', 'ACCESSIBLE')",
            ("diet-doc-11", "/kb/14day_diet_supplements_final.xlsx#11"),
        )
        connection.execute(
            "INSERT INTO chunks (chunk_id, document_id, text, heading_path)"
            " VALUES (?, ?, ?, ?)",
            (
                "diet-row-11",
                "diet-doc-11",
                "[Diet+Supplements_14days] Day=11 | Breakfast=구운계란2+아몬드 | Lunch=닭가슴살+현미밥1/3 | Dinner=두부+아보카도",
                "table-row-Diet+Supplements_14days-11",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    predicted = predict_prefetchable_spoken_response(
        "다이어트 식단표 에서 9일차 점심 하고 11일차 저녁 메뉴 알려줘",
        data_dir=data_dir,
    )

    assert predicted == "9일차 점심은 닭가슴살과 현미밥 이 분의 일입니다. / 11일차 저녁은 두부와 아보카도입니다."
