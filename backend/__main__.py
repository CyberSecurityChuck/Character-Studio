import uvicorn

from backend.configuration import load_settings
from backend.main import create_app


def main():
    settings = load_settings()
    # Loopback binding is intentionally not configurable in the local-only MVP.
    uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
