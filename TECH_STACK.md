# MomFit 기술 스택 기준 버전

| 기술 | 기준 버전 |
| --- | --- |
| Python | 3.12.x |
| FastAPI | 0.143.5 |
| Uvicorn | 0.53.0 |
| Pydantic | 2.14.1 |
| SQLAlchemy | 2.0.55 |
| MySQL | 8.4 LTS |
| NumPy | 2.5.4 |
| OpenCV | 5.0.0.93 |
| MediaPipe | 1.1.1 |
| Ultralytics YOLO | 8.4.175 |

위 버전은 팀 공통 목표 버전이다. 현재 `requirements.txt`에는 FastAPI 실행에 필요한 직접 의존성만 포함한다. NumPy, OpenCV, MediaPipe, Ultralytics YOLO는 아직 설치하지 않는다.

MediaPipe와 Ultralytics YOLO는 각각 OpenCV 의존성을 가질 수 있어, 향후 함께 도입할 때 OpenCV 및 관련 의존성의 호환성을 실제 설치 환경에서 검증해야 한다. 이 문서는 해당 호환성을 확정하지 않는다.
