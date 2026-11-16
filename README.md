# IBD Rx Agent

FastAPI 백엔드와 React(Vite) 프론트엔드로 구성된 개발 환경입니다.

## 실행

백엔드와 프론트엔드는 각각 터미널에서 실행합니다.

```bash
# 백엔드 (http://127.0.0.1:8000)
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
# 프론트엔드 (http://localhost:5173)
cd frontend
npm run dev
```

프론트엔드는 `/api` 요청을 백엔드로 프록시합니다. 상태 확인은 `GET /api/health` 입니다.

API 문서는 백엔드를 실행한 뒤 http://127.0.0.1:8000/docs 에서 볼 수 있습니다.

## Docker

Docker Desktop이 실행 중이어야 합니다. 프로젝트 루트에서 백엔드와 프론트엔드를 함께 띄웁니다.

```bash
docker compose up --build
```

- 프론트엔드: http://localhost:5173
- 백엔드: http://localhost:8001
- API 문서: http://localhost:8001/docs

호스트의 8000번 포트는 다른 프로세스가 이미 사용 중이라, Docker 백엔드는 8001번으로 열어둡니다. 컨테이너 내부 포트는 8000입니다.

컨테이너 안의 프론트엔드는 `http://backend:8000`으로 API를 프록시합니다. 로컬에서 `npm run dev`로 실행할 때는 기존처럼 `http://127.0.0.1:8000`을 사용합니다.

종료는 `Ctrl+C` 후 다음 명령입니다.

```bash
docker compose down
```

## 의존성 다시 설치

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```bash
cd frontend
npm install
```
