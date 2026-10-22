"""공통 컬럼 타입."""

from sqlalchemy import BigInteger, Integer

# MySQL은 BIGINT, SQLite(테스트)는 INTEGER. SQLite는 INTEGER PRIMARY KEY만 자동 증가하기 때문이다.
BigIntId = BigInteger().with_variant(Integer, "sqlite")
