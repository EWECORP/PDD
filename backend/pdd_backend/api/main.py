from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("PDD_API_HOST", "127.0.0.1")
    port = int(os.getenv("PDD_API_PORT", "8088"))
    workers = int(os.getenv("PDD_API_WORKERS", "2"))
    uvicorn.run(
        "pdd_backend.api.app:app",
        host=host,
        port=port,
        workers=workers,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("PDD_API_FORWARDED_ALLOW_IPS", "127.0.0.1"),
        access_log=True,
    )


if __name__ == "__main__":
    main()
