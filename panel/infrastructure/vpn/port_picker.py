from __future__ import annotations

import random
import socket


def pick_port(candidates: list[int], *, exclude: set[int] | None = None) -> int:
    blocked = exclude or set()
    pool = [port for port in candidates if port not in blocked]
    if not pool:
        pool = list(candidates)
    if not pool:
        raise ValueError("port_candidates must not be empty")

    random.shuffle(pool)
    for port in pool:
        if _is_port_free(port):
            return port
    return pool[0]


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True
