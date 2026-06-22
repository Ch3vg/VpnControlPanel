from __future__ import annotations

import random
import socket


class PortUnavailableError(ValueError):
    pass


def is_port_available(port: int, *, udp: bool = False, host: str = "0.0.0.0") -> bool:
    family = socket.AF_INET
    sock_type = socket.SOCK_DGRAM if udp else socket.SOCK_STREAM
    with socket.socket(family, sock_type) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def pick_port(
    candidates: list[int],
    *,
    exclude: set[int] | None = None,
    udp: bool = False,
) -> int:
    blocked = exclude or set()
    pool = [port for port in candidates if port not in blocked]
    if not pool:
        pool = list(candidates)
    if not pool:
        raise ValueError("port_candidates must not be empty")

    random.shuffle(pool)
    for port in pool:
        if is_port_available(port, udp=udp):
            return port

    proto = "UDP" if udp else "TCP"
    raise PortUnavailableError(
        f"No free {proto} port among candidates {candidates}"
        + (f" (excluded in DB: {sorted(blocked)})" if blocked else ""),
    )
