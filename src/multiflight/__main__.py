from __future__ import annotations

import uvicorn

from .settings import APP_HOST, APP_PORT


if __name__ == "__main__":
    uvicorn.run(
        "multiflight.main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=False,
    )
