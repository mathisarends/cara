import logging

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main() -> None:
    uvicorn.run("gateway.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
