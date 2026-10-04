# 주식 커뮤니티 데이터 수집 프로젝트

주식 커뮤니티의 게시글을 수집·저장하는 자동화 수집기를 만드는 개인 학습 프로젝트입니다. 첫 대상은 디시인사이드 나스닥 갤러리입니다.

## 학습 목표

- Python으로 HTTP 요청, HTML 파싱, 데이터 저장과 실패 처리 학습
- Docker 실행 환경 구성과 배치 스케줄링·클라우드 배포 학습
- AWS EC2의 기본 서버 운영, 권한·저장소·로그 관리 학습

## 진행 계획

1. 목록 HTML을 샘플로 저장하고 제목·글 번호·URL 등의 정보를 추출합니다.
2. 상세 본문 수집, SQLite 저장, 중복 방지와 실패 복구를 추가합니다.
3. 간단한 조회 UI와 Docker 실행을 검증합니다.
4. AWS에서 하루 한 번 수집하고 작업 후 서버를 중지하도록 자동화합니다.
5. 게시글 수집을 완성한 뒤 댓글 수집·갱신으로 확장합니다.

현재는 `crawl_test.py`로 PC 목록 한 페이지의 HTML 확보·샘플 파싱·JSON 저장을 구현한 단계입니다. 본문·댓글·DB와 Docker·AWS 배포는 아직 구현하지 않았습니다.

## 개발 환경

- Python 3.14.6 (`.python-version` 기준)
- uv: 가상환경 및 의존성 관리
- requests, BeautifulSoup: 요청 및 HTML 파싱
- 후속 도입: SQLite, Streamlit, Docker, AWS EC2

Mac 또는 Windows에 uv를 설치한 뒤 프로젝트 폴더에서 실행합니다.

```bash
uv sync --locked
uv run python --version
```

가상환경을 따로 활성화하지 않아도 `uv run`으로 실행할 수 있습니다. `.venv`는 컴퓨터마다 새로 만들고, `pyproject.toml`, `uv.lock`, `.python-version`을 공유합니다.

## 첫 테스트 실행

```bash
uv run crawl_test.py
```

기본은 `sample` 모드이며 `samples/nasdaq_list.html`과 응답 메타데이터를 읽습니다. 샘플은 Git에 포함하지 않으므로 새 컴퓨터에서는 먼저 코드 상단의 `RUN_MODE`를 `"capture"`로 바꿔 한 번 확보하고, 다시 `"sample"`로 바꿔 반복 검증합니다. `"live"`는 새 응답을 파싱하며 HTML을 저장하지 않습니다. 샘플이 없으면 자동으로 웹에 요청하지 않습니다.

추출 결과는 터미널과 `output/`의 JSON에서 확인할 수 있습니다. 네트워크 없는 합성 예제 검증은 다음 명령으로 실행합니다.

```bash
uv run python -m unittest discover -s tests -v
```

## 문서

- [프로젝트 기획서](docs/PROJECT_PLAN.md)
- [첫 크롤링 테스트 개발 전략](docs/CRAWL_TEST_STRATEGY.md)
- [실행 환경 설계 전략](docs/ENVIRONMENT_STRATEGY.md) — 초기 venv·pip 기준 문서이며, 현재 환경 관리는 uv를 사용합니다.

실제 수집 샘플과 생성 결과는 Git 추적에서 제외합니다. 실사이트 요청 전 수집 정책과 허용 범위를 확인하며, 관련 검토는 기획서에 정리합니다.
