"""`python -m app` starts the API with host, port, reload and log level taken from `.env`."""

import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
        log_config=None,  # our logging config (console + rotating files) handles uvicorn too
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
