from fastapi import FastAPI

app = FastAPI(title="admin-service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "admin"}
