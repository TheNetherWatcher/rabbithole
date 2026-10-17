#!/usr/bin/env python3
"""How many times can one captured 0-RTT flight run?  Models the RFC 8446 section 8 defenses:
freshness check (8.3) and ClientHello recording (8.2), for different cache layouts.

    python3 sim.py            # defaults: 8 servers, 10 s window, 50 replay attempts
    python3 sim.py 16 5 200   # servers, window seconds, replay attempts
"""
import hashlib
import os
import sys

N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
WINDOW_MS = int(float(sys.argv[2]) * 1000) if len(sys.argv) > 2 else 10_000
ATTEMPTS = int(sys.argv[3]) if len(sys.argv) > 3 else 50
M32 = 2**32


class Ticket:
    def __init__(self, now_ms):
        self.age_add = int.from_bytes(os.urandom(4), "big")  # ticket_age_add: fresh random 32 bits
        self.created_ms = now_ms  # server-side creation time (RTT estimate taken as 0 here)


def client_hello(ticket, now_ms):
    age_ms = now_ms - ticket.created_ms
    obfuscated = (age_ms + ticket.age_add) % M32  # RFC 8446 4.2.11.1
    binder = hashlib.sha256(os.urandom(16)).digest()  # stands in for the PSK binder: unique per ClientHello
    return {"obf_age": obfuscated, "binder": binder}


class Node:
    """One server instance. cache is where it records ClientHellos (shared or private)."""

    def __init__(self, ticket, cache, use_freshness=True):
        self.ticket, self.cache, self.fresh = ticket, cache, use_freshness

    def accepts_0rtt(self, ch, now_ms):
        if self.fresh:
            client_age = (ch["obf_age"] - self.ticket.age_add) % M32  # RFC 8446 8.3
            expected_arrival = self.ticket.created_ms + client_age
            if abs(expected_arrival - now_ms) > WINDOW_MS:
                return False  # stale: fall back to 1-RTT
        if self.cache is not None:
            if ch["binder"] in self.cache:
                return False  # seen before
            self.cache.add(ch["binder"])
        return True


def run(label, make_nodes, replay_delay_ms=1000, **kw):
    t = Ticket(now_ms=0)
    nodes = make_nodes(t)
    ch = client_hello(t, now_ms=60_000)  # client uses the ticket one minute after issue
    first = nodes[0].accepts_0rtt(ch, 60_000)
    runs = 1 if first else 0
    for i in range(ATTEMPTS):  # attacker replays the identical flight, round-robin over nodes
        runs += nodes[(i + 1) % len(nodes)].accepts_0rtt(ch, 60_000 + replay_delay_ms)
    print(f"{label:<46} runs of one request: {runs}")


print(f"{N} servers, window +/-{WINDOW_MS // 1000}s, {ATTEMPTS} replay attempts, replay arrives 1 s after the original\n")
run("no replay protection at all", lambda t: [Node(t, None, False) for _ in range(N)])
run("freshness window only", lambda t: [Node(t, None, True) for _ in range(N)])
run("freshness + one cache per server", lambda t: [Node(t, set(), True) for _ in range(N)])


def shared(t):
    c = set()
    return [Node(t, c, True) for _ in range(N)]


run("freshness + one shared cache", shared)
run("freshness + cache, replay after window closes", shared, replay_delay_ms=WINDOW_MS + 5_000)
