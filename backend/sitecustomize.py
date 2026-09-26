"""Startup logging hook for local diagnostic runs.

Python automatically imports ``sitecustomize`` when this directory is on
``sys.path``. The handler below mirrors only AGENT_DIAG records into a file so
normal application logs do not make the diagnostic trace difficult to read.
"""

import logging
from pathlib import Path


class _AgentDiagnosticFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().startswith("AGENT_DIAG")


LOG_PATH = Path(__file__).resolve().parent / "agent_diagnostics.log"


def _install_agent_diagnostics_file_handler() -> None:
    root_logger = logging.getLogger()
    resolved_path = str(LOG_PATH.resolve())

    # Avoid duplicate handlers if an application reload imports this module
    # more than once in the same interpreter process.
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                if str(Path(handler.baseFilename).resolve()) == resolved_path:
                    return
            except Exception:
                continue

    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setLevel(logging.WARNING)
    handler.addFilter(_AgentDiagnosticFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )
    root_logger.addHandler(handler)


_install_agent_diagnostics_file_handler()
