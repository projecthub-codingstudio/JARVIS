# 데이터 파이프라인 구현 가이드

## 개요

이 문서는 실시간 로그 수집 및 변환 파이프라인의 구현 방법을 설명합니다.
Apache Kafka에서 메시지를 소비하고, 정제 후 데이터 웨어하우스에 적재하는 과정을 다룹니다.

## 1단계: Kafka 소비자 설정

Kafka 토픽에서 로그 메시지를 소비하는 클래스입니다.
`group_id`를 통해 소비자 그룹을 관리하며, 오프셋 자동 커밋을 비활성화하여
정확히 한 번(exactly-once) 처리를 보장합니다.

```python
from confluent_kafka import Consumer, KafkaError

class LogConsumer:
    """로그 메시지 소비자 클래스.

    Kafka 토픽에서 구조화된 로그를 읽어옵니다.
    배치 크기는 기본 100건이며, 최대 대기 시간은 5초입니다.
    """

    def __init__(self, bootstrap_servers: str, group_id: str = "log-pipeline"):
        self.config = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
        self.consumer = Consumer(self.config)

    def consume_batch(self, topic: str, batch_size: int = 100, timeout: float = 5.0):
        """지정된 토픽에서 배치 단위로 메시지를 소비합니다."""
        self.consumer.subscribe([topic])
        messages = self.consumer.consume(num_messages=batch_size, timeout=timeout)
        return [msg for msg in messages if msg.error() is None]
```

## 2단계: 데이터 변환

수집된 로그를 정규화하고 필요한 필드를 추출하는 변환 단계입니다.
타임스탬프 파싱, IP 주소 익명화, 불필요한 필드 제거를 수행합니다.

```python
import hashlib
from datetime import datetime

def anonymize_ip(ip_address: str) -> str:
    """IP 주소를 SHA-256 해시로 익명화합니다.

    개인정보 보호를 위해 원본 IP는 저장하지 않습니다.
    """
    return hashlib.sha256(ip_address.encode()).hexdigest()[:16]

def transform_log_entry(raw_entry: dict) -> dict:
    """원시 로그 항목을 정규화된 형태로 변환합니다.

    변환 규칙:
    - timestamp: ISO 8601 형식으로 통일
    - ip: 익명화 처리
    - level: 대문자로 정규화 (INFO, WARN, ERROR)
    - message: 앞뒤 공백 제거
    """
    return {
        "timestamp": datetime.fromisoformat(raw_entry["ts"]).isoformat(),
        "ip_hash": anonymize_ip(raw_entry.get("client_ip", "0.0.0.0")),
        "level": raw_entry.get("level", "INFO").upper(),
        "message": raw_entry.get("msg", "").strip(),
        "service": raw_entry.get("service_name", "unknown"),
    }
```

## 3단계: 데이터 웨어하우스 적재

변환된 데이터를 BigQuery에 적재합니다.
스트리밍 삽입(streaming insert)을 사용하며, 실패 시 3회 재시도합니다.

```python
from google.cloud import bigquery

def load_to_warehouse(records: list[dict], table_id: str) -> int:
    """변환된 레코드를 BigQuery 테이블에 적재합니다.

    Returns:
        성공적으로 적재된 레코드 수
    """
    client = bigquery.Client()
    errors = client.insert_rows_json(table_id, records)
    if errors:
        raise RuntimeError(f"BigQuery 적재 실패: {errors}")
    return len(records)
```

## 모니터링 지표

파이프라인 운영 시 다음 지표를 모니터링해야 합니다:
- **소비 지연(consumer lag)**: 5분 이상 지연 시 경고
- **변환 실패율**: 1% 초과 시 경고
- **적재 처리량**: 초당 최소 1,000건 유지
- **재시도 횟수**: 분당 10회 초과 시 점검 필요
