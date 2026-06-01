from fastapi import FastAPI

app = FastAPI(title="matching-service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "matching"}
