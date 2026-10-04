# Python 가상환경과 Docker 실행 환경 전략

## 간단한 정리

**로컬 학습·디버깅에는 프로젝트 전용 `.venv`, 실행 재현·AWS 배포에는 Docker를 사용한다.** 코드는 동일하게 유지하고 Python 버전과 의존성 목록을 맞춘다. 로컬 가상환경을 Docker나 AWS에 복사하지 않는다.

- 초기 도구: Python 표준 venv + pip + requirements.txt.
- 초기 외부 라이브러리: requests, beautifulsoup4만 직접 설치.
- 현재 확인: Python 3.14.6 (`/opt/homebrew/bin/python3`), Docker CLI 29.6.1.
- 미확인: 라이브러리 설치 호환성, Docker 엔진 실행 여부, Linux 이미지 실행 결과.
- 이 문서는 설계이며 가상환경 생성·설치·이미지 빌드는 아직 수행하지 않았다.

## 1. 역할 구분

| 구성 | 역할 | 사용 시점 |
| --- | --- | --- |
| 로컬 `.venv` | 프로젝트의 Python 패키지를 다른 프로젝트와 분리 | HTML 관찰, 파서 개발, 디버깅 |
| `requirements.txt` | 검증한 패키지 버전을 기록하고 재설치 | 로컬 환경 재생성, Docker 빌드 |
| Docker 이미지 | Python·라이브러리·코드·Linux 실행 환경 구성 | 초기 실행 확인, 재현성 검증, AWS 배포 |

venv는 기반 Python 위에서 패키지를 격리하며 Python 자체의 버전 관리나 운영체제 격리를 대신하지 않는다. Docker와 venv는 역할이 겹치는 부분이 있지만, 로컬 디버깅 편의와 배포 환경 검증을 위해 함께 사용한다. 컨테이너 안의 별도 venv는 첫 단일 앱 이미지에 필수로 추가하지 않는다.

## 2. Python 버전 정책

현재 설치된 Python 3.14.6을 첫 로컬 검증 후보로 사용한다. 최신 버전이라는 이유만으로 바꾸거나 다른 버전을 추가 설치하지 않는다. 두 라이브러리 설치와 파서 실행을 확인한 뒤 프로젝트 버전을 기록한다.

Docker에서도 같은 Python major/minor 버전을 사용하고 가능한 경우 patch 버전까지 맞춘다. 실제 이미지 태그 존재 여부를 확인하고 검증한 태그 또는 digest를 기록한다. 최신 태그에 자동으로 따라가지 않는다.

호환 문제가 발견되면 원인을 확인한 뒤 지원되는 Python 버전으로 로컬과 Docker를 함께 변경한다. venv를 생성한 후 기반 Python 버전이 바뀌면 기존 환경을 임의로 재사용하지 않고 다시 만든다.

## 3. 가상환경 생성·사용 계획

아래 명령은 프로젝트 루트에서 수행할 예정이며 아직 실행하지 않았다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
python -m pip --version
python -m pip install requests beautifulsoup4
python -m pip check
python -c "import sys, requests, bs4; print(sys.executable); print(requests.__version__, bs4.__version__)"
```

`python -m pip`를 사용해 실행할 Python과 설치 대상이 일치하도록 한다. 전역 Python에 패키지를 설치하지 않는다. 에디터의 인터프리터도 `.venv/bin/python`으로 지정한다. 활성화 없이 `.venv/bin/python crawl_test.py`로 실행할 수도 있다.

## 4. 의존성 기록과 재생성

깨끗한 프로젝트 가상환경에서 필요한 두 라이브러리와 자동 설치된 의존성만 검증한다. 성공한 상태를 다음 명령으로 기록한다.

```bash
python -m pip freeze > requirements.txt
```

`requirements.txt`는 직접 의존성과 하위 의존성의 검증 버전을 기록한다. 라이브러리를 아직 설치하지 않았으므로 버전 번호를 미리 추측해 작성하지 않는다. pip·Python 버전은 별도로 기록한다.

재생성 시에는 선택한 Python으로 새 venv를 만들고 `python -m pip install -r requirements.txt`를 실행한다. `.venv` 디렉터리 자체를 공유하지 않는다. 버전 고정만으로 Mac과 Linux의 완전 동일성을 보장하지 않으므로 Docker 안에서도 설치·import·샘플 파싱을 확인한다.

## 5. Docker 연결

- Python 코드와 requirements.txt로 Linux 이미지를 만든다. 호스트 `.venv`는 복사하지 않는다.
- 개발 시 코드·samples를 마운트하고 output은 외부에 보존한다. samples 읽기와 capture 쓰기의 마운트 권한은 실행 모드에 맞춘다.
- 호스트 절대 경로를 코드에 넣지 않고 스크립트 위치 기준으로 데이터 경로를 계산한다.
- Mac 로컬과 EC2에서 이미지 CPU 아키텍처가 맞는지 확인한다.
- Docker 안에서 pip check, 라이브러리 import, sample 모드 실행을 검증한다. 네트워크 요청 없이도 결과를 비교할 수 있다.
- 실제 운영에는 검증한 이미지를 배포한다. 로컬 실행만 성공한 상태를 클라우드 검증 완료로 보지 않는다.

Docker 엔진 실행 여부와 이미지 가용성은 실제 빌드 시 확인한다. Docker CLI 버전 확인은 엔진이나 컨테이너 실행 성공을 뜻하지 않는다.

## 6. 파일 관리

계획한 구조:

```text
data-crawling-project/
  .venv/                 # 로컬 전용, Git·Docker 빌드 제외
  requirements.txt       # 검증 버전, Git 포함
  crawl_test.py           # 테스트 Python 소스 하나
  Dockerfile              # 이미지 정의, 환경 구현 단계에서 추가
  .gitignore
  .dockerignore
  samples/                # 학습용 HTML·메타데이터
  output/                 # 생성 JSON
  docs/                   # 기획·전략 문서
```

`.venv`, `__pycache__`, 생성 결과, 로컬 인증 정보는 Git과 Docker 빌드 문맥에서 제외한다. 실제 수집 샘플은 기본적으로 Git에 올리지 않고 합성 테스트 예제는 구분해 관리한다. `.env`는 실제 설정 필요가 생길 때 추가하며 첫 고정 URL 테스트에는 필요 없다.

## 7. 환경 준비 완료 기준

1. 프로젝트 venv의 Python으로 실행되는지 확인.
2. 두 라이브러리 import 성공과 pip check 통과.
3. 검증한 Python·패키지 버전 기록과 requirements.txt 준비.
4. 코드 작성 후 로컬과 Docker에서 동일 샘플의 게시글 결과 비교.
5. 컨테이너 재생성 후에도 샘플·결과 보존 확인.

로컬 환경 검증 후 HTML 확보·관찰·파서 개발을 시작한다. Docker도 초기 테스트부터 사용하되, 이미지 재현성과 AWS 배포 검증은 전체 학습 계획의 단계에 맞춰 수행한다. uv·Poetry·Conda 등 추가 환경 관리 도구는 현재 범위에 도입하지 않는다.

참고: [Python venv 문서](https://docs.python.org/3/library/venv.html), [Docker 이미지 빌드 권장사항](https://docs.docker.com/build/building/best-practices/).
