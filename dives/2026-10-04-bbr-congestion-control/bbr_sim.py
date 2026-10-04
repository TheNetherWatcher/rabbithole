#!/usr/bin/env python3
"""Toy packet-level sim: one bottleneck, one sender, BBR-ish vs Reno-ish.

Not a faithful kernel model. It reproduces the *shape* of the behaviour:
  - Reno fills the buffer until it drops, so RTT inflates to (buffer / rate).
  - BBR finds BtlBw via max-filter of delivery-rate samples and RTprop via
    min-filter of RTT, then paces near BtlBw with a small 1.25/0.75 probe,
    keeping the queue near empty regardless of buffer size.

Usage:  python3 bbr_sim.py              # default 12 Mbit/s, 40 ms, buffer 8 BDP
        python3 bbr_sim.py --buf 0.5    # shallow buffer (in BDPs)
"""
import argparse
import math
from collections import deque

MSS = 1500 * 8  # bits per packet


def run(cca, rate_mbps=12.0, rtprop_ms=40.0, buf_bdp=8.0, secs=12.0, verbose=False):
    dt = 0.0005  # 0.5 ms tick
    rate = rate_mbps * 1e6 / MSS          # bottleneck, packets/s
    rtprop = rtprop_ms / 1000.0
    bdp = rate * rtprop                   # packets
    buf_cap = max(1, int(buf_bdp * bdp))

    queue = deque()          # send timestamps of packets waiting at bottleneck
    in_net = deque()         # (ack_arrival_time, (send_time, delivered_at_send, delivered_time_at_send))
    serve_credit = 0.0
    delivered = 0            # packets ACKed
    delivered_time = 0.0
    inflight = 0
    drops = 0

    # BBR state
    bw_samples = deque()     # (round, rate)
    round_count, next_round_delivered = 0, 0
    btlbw, rtprop_est, rtprop_stamp = 0.0, float("inf"), 0.0
    state, cycle_idx, cycle_stamp = "STARTUP", 0, 0.0
    full_bw, full_cnt = 0.0, 0
    probe_rtt_done = None
    gains = [1.25, 0.75, 1, 1, 1, 1, 1, 1]
    pacing_credit = 0.0

    # Reno state
    cwnd, ssthresh = 10.0, float("inf")

    t, log, rtts = 0.0, [], []
    last_log = -1
    while t < secs:
        t += dt
        # --- bottleneck serves packets
        serve_credit += rate * dt
        while queue and serve_credit >= 1:
            serve_credit -= 1
            snd = queue.popleft()
            in_net.append((t + rtprop, snd))  # rest of the path + ACK return
        if not queue:
            serve_credit = min(serve_credit, 1.0)

        # --- ACK arrivals
        while in_net and in_net[0][0] <= t:
            _, (snd, d_at_send, dt_at_send) = in_net.popleft()
            inflight -= 1
            delivered += 1
            delivered_time = t
            rtt = t - snd
            rtts.append((t, rtt))
            if cca == "bbr":
                interval = max(t - dt_at_send, rtt)
                if interval > 0:
                    bw_samples.append((round_count, (delivered - d_at_send) / interval))
                if d_at_send >= next_round_delivered:
                    next_round_delivered = delivered
                    round_count += 1
                    # full-pipe detection: <25% growth for 3 rounds
                    if state == "STARTUP":
                        if btlbw >= full_bw * 1.25:
                            full_bw, full_cnt = btlbw, 0
                        else:
                            full_cnt += 1
                            if full_cnt >= 3:
                                state = "DRAIN"
                while bw_samples and bw_samples[0][0] < round_count - 10:
                    bw_samples.popleft()
                btlbw = max(r for _, r in bw_samples)
                if rtt <= rtprop_est or t - rtprop_stamp > 10:
                    rtprop_est, rtprop_stamp = rtt, t
            else:
                if cwnd < ssthresh:
                    cwnd += 1
                else:
                    cwnd += 1 / cwnd

        # --- sender decides
        if cca == "bbr":
            bdp_est = btlbw * (rtprop_est if rtprop_est < 1e9 else rtprop)
            if state == "DRAIN" and inflight <= bdp_est:
                state, cycle_idx, cycle_stamp = "PROBE_BW", 2, t
            if state == "PROBE_BW" and t - cycle_stamp > rtprop_est:
                cycle_idx, cycle_stamp = (cycle_idx + 1) % 8, t
            if state != "PROBE_RTT" and t - rtprop_stamp > 10:
                state, probe_rtt_done = "PROBE_RTT", t + 0.2
            if state == "PROBE_RTT" and t >= probe_rtt_done:
                rtprop_stamp = t
                state, cycle_idx, cycle_stamp = "PROBE_BW", 2, t
            pg = {"STARTUP": 2 / math.log(2), "DRAIN": math.log(2) / 2,
                  "PROBE_RTT": 1.0}.get(state, gains[cycle_idx])
            cg = 2 / math.log(2) if state == "STARTUP" else 2.0
            win = 4 if state == "PROBE_RTT" else max(4, cg * bdp_est) if btlbw else 10
            pace = pg * btlbw if btlbw else 10 / rtprop
            pacing_credit = min(pacing_credit + pace * dt, 2)
            can_send = lambda: pacing_credit >= 1 and inflight < win
        else:
            can_send = lambda: inflight < int(cwnd)

        while can_send():
            if cca == "bbr":
                pacing_credit -= 1
            inflight += 1
            pkt = (t, delivered, delivered_time if delivered else t)
            if len(queue) >= buf_cap:
                drops += 1
                inflight -= 1  # dropped: treat as instantly detected loss (toy)
                if cca == "reno":
                    ssthresh = max(cwnd / 2, 2)
                    cwnd = ssthresh
                continue
            queue.append(pkt)

        if int(t * 10) != last_log:
            last_log = int(t * 10)
            log.append((round(t, 1), state if cca == "bbr" else "-", len(queue),
                        round(btlbw * MSS / 1e6, 2) if cca == "bbr" else None))

    goodput = delivered * MSS / secs / 1e6
    late = [r for (tt, r) in rtts if tt > secs / 2]
    med = sorted(late)[len(late) // 2] if late else float("nan")
    return dict(cca=cca, bdp_pkts=round(bdp, 1), buf_pkts=buf_cap, goodput_mbps=round(goodput, 2),
                median_rtt_ms=round(med * 1000, 1), drops=drops, log=log)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=12.0)
    ap.add_argument("--rtt", type=float, default=40.0)
    ap.add_argument("--buf", type=float, default=8.0, help="buffer size in BDPs")
    ap.add_argument("--trace", action="store_true", help="print BBR state every 100 ms for first 1.5 s")
    a = ap.parse_args()
    for cca in ("reno", "bbr"):
        r = run(cca, a.rate, a.rtt, a.buf)
        print(f"{cca:5s} bdp={r['bdp_pkts']}pkt buf={r['buf_pkts']}pkt goodput={r['goodput_mbps']}Mbit/s "
              f"median_rtt(2nd half)={r['median_rtt_ms']}ms drops={r['drops']}")
        if a.trace and cca == "bbr":
            for row in r["log"][:16]:
                print("   t=%.1fs state=%-9s queue=%3d pkts btlbw=%s Mbit/s" % row)


if __name__ == "__main__":
    main()
