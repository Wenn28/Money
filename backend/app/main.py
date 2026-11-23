from fastapi import FastAPI

app = FastAPI(title="Saham")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
