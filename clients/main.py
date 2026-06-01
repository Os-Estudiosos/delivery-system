from fastapi import FastAPI

app = FastAPI(title="clients-service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "clients"}
