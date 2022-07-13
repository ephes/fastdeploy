postgres: postgres -D databases/postgres
uvicorn: PYTHONUNBUFFERED=true uvicorn deploy.entrypoints.fastapi_app:app --reload
mkdocs: mkdocs serve -a 127.0.0.1:8001
# jupyterlab: PYTHONPATH=$(pwd) jupyter-lab
vue: cd frontend && npm run dev
