#!/usr/bin/env python
from __future__ import annotations
"""FPDB API - Web API server entry point"""

import uvicorn

if __name__ == "__main__":
    # Use import string with factory for reload support
    uvicorn.run(
        "fpdb.presentation.api:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload during development
    )
