import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,  # uvicorn configures the root logger before this runs;
                     # without force=True, basicConfig() is a silent no-op.
    )
