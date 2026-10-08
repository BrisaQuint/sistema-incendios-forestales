def main() -> None:
    import uvicorn

    from sistema_incendios_forestales.api.app import app

    uvicorn.run(app, host="127.0.0.1", port=8000, workers=1)
