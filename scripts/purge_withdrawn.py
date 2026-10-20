"""유예 기간이 지난 탈퇴 계정을 삭제한다. 서버의 주기 작업과 같은 로직이며, 수동이나 cron으로 실행할 수 있다.

    python -m scripts.purge_withdrawn
"""

import logging

from services.account_service import run_purge


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    count = run_purge()
    print(f"삭제한 탈퇴 계정: {count}건")


if __name__ == "__main__":
    main()
