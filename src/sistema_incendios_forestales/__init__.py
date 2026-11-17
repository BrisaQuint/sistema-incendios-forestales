def main() -> None:
    import logging
    import os
    import uvicorn
    from sistema_incendios_forestales.operational_logging import configure_logging

    from sistema_incendios_forestales.api.app import app

    handler = configure_logging(os.environ)
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000, workers=1, log_config=None)
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
