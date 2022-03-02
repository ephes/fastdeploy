postgres: postgres -D databases/postgres
uvicorn: uvicorn deploy.entrypoints.fastapi_app:app --reload
mkdocs: mkdocs serve -a 127.0.0.1:8001
jupyterlab: DATABASE_URL=postgresql:///deploy PYTHONPATH=$(pwd) jupyter-lab
