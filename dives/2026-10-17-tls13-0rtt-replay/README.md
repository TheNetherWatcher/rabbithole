# TLS 1.3 0-RTT early data: replay windows, ticket age, and idempotency

**Computer science · Networking/protocols · TLS 1.3 0-RTT early data: PSK resumption, anti-replay windows, why idempotency is the app’s problem · hard**

A TLS 1.3 client holding a resumption ticket can send its request in the **first flight**, encrypted with a key made from the ticket alone. That saves **one round trip**, but no fresh server randomness is involved, so a network attacker can **replay** it. Servers fight back with a **replay cache** and a **~10 s freshness window**, yet a cluster only gets “at most once per server”.
**Why it matters:** 0-RTT is a real latency win for reads and a real double-charge risk for writes, and the line between them is drawn by your application, not by TLS.

## Cold open

You tap “Pay” in an app. Your phone fires one encrypted packet at the server.

A stranger on the café wifi can’t read it, can’t change it. But they *can* copy it and send it again. The protocol that made it fast, TLS 1.3 *0-RTT*, has no built-in way to say “this is the second copy”.

## Scroll story

You open a shop's app. Your phone and the shop's server do a **handshake**: a few messages to agree on secret keys. At the end the server hands your phone a **ticket**, a small sealed token meaning “this client was here before”.

**The next visit is faster, but not free.** The phone shows the ticket and the two sides resume. Even so, the first real request (`GET /cart`) waits for one full round trip. On a 100 ms path that is 100 ms of staring at nothing.

**0-RTT removes that wait.** The phone encrypts `GET /cart` with a key made from the ticket and sends it in the *very first* flight, glued to the ClientHello. The server can start work the moment the flight lands.

**The catch is in the key.** It is built only from the ticket's secret and the ClientHello. The server has contributed no fresh randomness, so nothing ties these bytes to *this* connection. That also means no forward secrecy for this data.

**So the flight can be copied.** An attacker on the path records the whole first flight and sends it again. Everything checks out: real ticket, real binder, correct key. The server has no way to call it a duplicate by cryptography alone.

**Defense one: remember.** The server stores a fingerprint of each accepted ClientHello (the PSK binder works). A second sighting means “refuse 0-RTT”: the handshake still completes, but the early data is thrown away and the client resends it safely.

**Defense two: forget on schedule.** The client says how old its ticket is. The server accepts early data only if that age fits the wall clock to within about ten seconds, so the cache only needs the last few seconds of entries, not all history.

**Real fleets break the memory.** If eight servers each keep their own cache, the attacker replays the flight to all eight. Each accepts it once. The RFC says outright that this “limits the number of replays to the number of server instances”.

**So: one round trip bought, replay not fully closed.** Treat early data like a request that may arrive twice, and put only safe-to-repeat requests in it. The cards below open each part.


## In everyday words: A returning customer can order before saying hello, and anyone can copy the order

Picture a coffee shop with a members’ card. The first time you visit, the staff chat with you, check who you are, and stamp a card that says “regular, known to us”. The next visit you skip the chat: you walk up and slide your card and a sealed order slip across the counter in the same motion. The slip is sealed with a code only you and the shop can compute from the card. The barista starts your flat white before saying hello. That is the whole trick of **0-RTT**: a returning customer’s first message already carries the order.

The catch is the photocopier. Anyone standing nearby can’t read the slip or change it, but they can copy the card and the sealed slip and hand both in again. To the barista the copy is perfect, and a second flat white gets made and charged. The fix is boring bookkeeping: the shop keeps a short log of slips it served in the last few seconds and refuses repeats. That works for one barista. With eight baristas who each keep their own log, the copy can be handed to each of them, and each makes one coffee.

### Everyday example

Maya’s grocery app gets a card (the “ticket”) when she first signs in, good for two days. Next morning she opens it and the phone sends *show my basket* in its very first packet. The server answers 100 ms sooner than it otherwise would. Someone who recorded that packet replays it: the server shows the basket again. Harmless.

Now suppose the packet had been *place my order*. The replay would place it twice. So the app’s rule is: only requests that are safe to repeat may travel this way. For anything else the server answers “425 Too Early, come back after the handshake”, and the phone sends it again through the normal, safe route.

## §1 · Bare-minimum context: Six ideas to bring along

- **RTT** is the round-trip time between client and server; every back-and-forth message pair costs one. [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446) §1 lists TLS 1.3’s handshake modes.

- **TLS 1.3 handshake**: ClientHello (with a key share) → ServerHello and Finished. Encryption keys come from HKDF over the shared secret, so a normal connection is already 1-RTT.

- **Resumption with a PSK**: after a connection the server sends a `NewSessionTicket`. Later the client offers it back as a pre-shared key (PSK) so the two skip certificates and key exchange.

- **AEAD records**: TLS wraps data in authenticated-encryption records; the attacker can neither read nor alter them, only drop, delay or duplicate.

- **Idempotent**: running a request twice has the same effect as once (a read, a `PUT` to a fixed value). `POST /charge` is the opposite. See [RFC 8470](https://www.rfc-editor.org/rfc/rfc8470).

- **QUIC** embeds TLS 1.3, so its 0-RTT is the same mechanism ([RFC 9001](https://www.rfc-editor.org/rfc/rfc9001)).

## §1b · Real-world context: nginx, QUIC and CDNs ship it, mostly for safe reads

### What it is

**TLS 1.3 early data** (“0-RTT”) lets a client that already holds a resumption ticket send application data in its *first flight*, glued to the ClientHello. The data is encrypted under a key derived from the ticket’s PSK, so the server can decrypt and act on it before the handshake finishes.

### Why it exists

A TLS 1.3 handshake costs one round trip before the first request can leave. On a 100 ms mobile path that is 100 ms on every cold connection, and for QUIC it is half of the total time to first response (2 RTT → 1 RTT). Operators who serve static pages and APIs from CDNs wanted that back. The cost is a security property: [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446) §2.3 says “there are no guarantees of non-replay between connections” for early data.

### Where it’s used

- **nginx** (1.15.3+, OpenSSL 1.1.1+ or BoringSSL): `ssl_early_data`, off by default; `$ssl_early_data` is `"1"` while the request is still in early data.

- **OpenSSL / BoringSSL**: the server-side hooks (`SSL_read_early_data`, `SSL_write_early_data`) and the library’s own anti-replay option. nginx notes the OpenSSL anti-replay is *disabled* by default because it breaks resumption.

- **QUIC / HTTP/3**: [RFC 9001 §9.2](https://www.rfc-editor.org/rfc/rfc9001#section-9.2) says endpoints “MUST implement and use the replay protections described in [TLS13], however it is recognized that these protections are imperfect.”

- **CDNs**: Cloudflare offers 0-RTT as a zone setting and tells origins about early-data requests with an `Early-Data: 1` header (per its docs as summarized in search results, not read in full; Trail of Bits’ 2019 post describes the same idea).

- **Go’s standard `crypto/tls`** has no early-data switch for TLS over TCP (I read the `Config` struct on pkg.go.dev); Go’s early data lives on the QUIC side.

- **HTTP layer**: [RFC 8470](https://www.rfc-editor.org/rfc/rfc8470) defines the `Early-Data: 1` request header and the `425 Too Early` status.

### How it’s used

Switch it on at the TLS terminator, then make the app aware of it:

```
# nginx
ssl_early_data on;
proxy_set_header Early-Data $ssl_early_data;     # origin sees "1" for early-data requests
# optional, off by default because it breaks resumption on OpenSSL:
# ssl_conf_command Options AntiReplay;
```

The origin then applies RFC 8470: if `Early-Data: 1` is present and the request is not safe to run twice, answer `425 Too Early`. A client that gets 425 MUST retry, and the retry MUST NOT be sent as early data.

### When to use it, when not to

**Use when** the early requests are reads (`GET`/`HEAD`/`OPTIONS` with no side effects), the latency win matters (mobile, intercontinental, first-paint), and you know where replay state lives.

**Skip when** requests change state (payments, orders, votes, counters), a GET has side effects, or you front a fleet that does not share replay state and cannot be sure the origin checks the header.

### Who should care

**Infra and CDN engineers** who flip the switch; **backend developers** whose endpoints suddenly receive replayed requests; **security reviewers** who must treat early data as replayable and not forward secret; **client authors** who decide what may go in early data and must handle rejection.

## §2 · The one-liner: “Saves a round trip” hides five costs

“0-RTT lets a returning client send its request in the first packet, so you save a round trip.”

- **It saves exactly one round trip, not “zero”.** A TLS 1.3 resumption is already 1-RTT; 0-RTT removes that one. Over TCP the TCP handshake is a separate round trip.

- **The data is replayable.** No fresh server randomness goes into its key, so a network attacker can resend the flight and every check passes.

- **It is not forward secret.** The early key comes from the PSK alone; whoever later gets the ticket-encryption key can decrypt recorded early data.

- **The server may refuse, silently.** It can skip the early data and complete a normal handshake. The client must be ready to resend.

- **Defenses need state, and fleets rarely share it.** The RFC’s minimum is “at most once per server instance”, which is not the same as once.

## §3 · The problem: Sending data before the handshake ends needs a key both sides already hold

**−1 RTT**the entire prize: one round trip off the first request

Every handshake message pair costs a full round trip, and round trips are the one cost that does not shrink with faster hardware. On a 100 ms path, here is the time until the first response byte arrives:

| Setup | Round trips before response | At 100 ms RTT |

| TCP + TLS 1.3, full handshake | 1 (TCP) + 1 (TLS) + 1 (request) | 300 ms |

| TCP + TLS 1.3, resumed (PSK) | same: the PSK removes certificates, not the round trip | 300 ms |

| TCP + TLS 1.3, 0-RTT | 1 (TCP) + 1 (request rides the first TLS flight) | 200 ms |

| QUIC 1-RTT | 1 (handshake) + 1 (request) | 200 ms |

| QUIC 0-RTT | 1 | 100 ms |

*(Figure: Message ladders for a full handshake, a 1-RTT resumption and a 0-RTT resumption: only the last lets the request leave in the first flight.)*
The obstacle is cryptographic. In a normal handshake both sides contribute fresh randomness (the ECDHE shares and the Random values), and the traffic keys are derived from all of it, so every connection’s keys are unique and a recorded message is useless on another connection. To send data *before* the server has said anything, the client has to encrypt under something both sides already know: the ticket’s PSK. That is the root of both properties that come with 0-RTT: **no forward secrecy** and **no replay protection**.

So the design problem is: gain the round trip, bound the damage of replays, and keep the whole thing optional so a server that cannot defend itself can say no.

## §4 · Mental model: A stamped card plus a sealed slip: copyable, not forgeable

A **stamped membership card plus a pre-sealed order slip**. The card proves “this person was here before”. The slip is sealed with a code derived from the card, so it is authentic and unreadable to onlookers. The shop can serve you before it has met you today.

**Where it breaks.** A card is a physical thing that you hand over and can get back; a TLS ticket is just bytes, so “spending” it once has no meaning unless the shop *records* that it was spent (single-use tickets, §8.1). A photocopied slip can be spotted by a human; a replayed flight is bit-identical, so only a shop-side log can catch it. And onlookers can’t forge a *new* order, only duplicate old ones, which is why the whole problem reduces to “is this order safe to run twice?”.

## §5 · The mechanism, traced: Ticket in, early key out, then accept or refuse

One returning client, one request. The numbers are made up but follow the RFC’s fields and arithmetic.

  ← Back
  Next →
  
  

```

```

### Where the early key comes from

*(Figure: How the early traffic secret is derived: from the resumption secret through the PSK and Early Secret, with no server input.)*
Everything on the left is known to both sides from the previous connection. Nothing the server sends today appears in the derivation. That is exactly why the data can be sent early, and exactly why it can be replayed.

### What the server does with the flight

*(Figure: The server’s four checks before it accepts early data; any “no” falls back to a normal handshake.)*
RFC 8446 §4.2.10 gives the server three ways to answer an `early_data` extension: ignore it and finish a normal 1-RTT handshake (skipping the early records by trial decryption, up to `max_early_data_size`), send a HelloRetryRequest, or accept by returning `early_data` in EncryptedExtensions. It cannot accept “some” of the records. Early data is also not allowed after a HelloRetryRequest.

### The replay

An attacker who copies the first flight gets a second run of steps 5–6 on whatever server receives it. Only the replay cache in step 5 can tell the copy apart from the original: the ticket, binder, key and age all still look valid.

## §6 · The math: A ±10 s window turns “remember everything” into megabytes

### Hiding and checking the ticket age

The server picks a random 32-bit *aadd* (`ticket_age_add`) for every ticket. The client measures how long it has held the ticket, *a* milliseconds, and sends

o = (a + aadd) mod 232     server: a′ = (o − aadd) mod 232

  _→ in plain terms: the client adds a secret random offset to its ticket age so a passive observer cannot match two connections by their ages; only the server, who chose the offset, can undo it._

Worked example: *aadd* = 0x9f3a1c52 = 2 671 385 682, age one hour = 3 600 000 ms, so *o* = 2 674 985 682 = 0x9f710ad2. The server recovers *a′* = 3 600 000.

The server stored (or sealed into the ticket) its creation time *Tc* and an RTT estimate, then predicts when the ClientHello *should* arrive:

E = Tc + R̂ + a′     accept 0-RTT iff |E − tnow| ≤ W

  _→ in plain terms: “the client says the ticket is an hour old; I issued it an hour ago, plus one network trip; so this flight should land about now. If it lands far from now, it is old or replayed.” W is about ten seconds for Internet clients (RFC 8446 §8.3)._

*(Figure: The ticket-age check: the server predicts when the ClientHello should arrive and accepts only a flight that lands near that time.)*
**Why the form?** A check on wall-clock time alone would require clients and servers to agree on clocks; using the *client’s own elapsed time* against the *server’s own issue time* needs only that clock *rates* match closely, which they do.

### How big is the replay cache?

The freshness window means an entry only has to live as long as a replay could still pass the age check, about 2W with a symmetric window.

M = λ · 2W · b

  _→ in plain terms: memory = accepted early-data handshakes per second × how long you must remember each × bytes per entry._

At λ = 10 000 accepts/s, W = 10 s, b = 32 bytes (a SHA-256 of the binder): M = 10 000 × 20 × 32 B = **6.4 MB**. Real hash tables add overhead, but this is nowhere near a scaling problem. The hard part is *coordination*, not RAM.

### A Bloom filter instead of a table

A probabilistic set is allowed if a false positive means “reject 0-RTT”, because the cost of a false positive is only the lost round trip. For n = 200 000 entries (the case above) and false-positive rate p:

m = −n ln p / (ln 2)2     k = (m/n) ln 2

  _→ in plain terms: bits needed grow with the log of how rarely you tolerate wrongly refusing a legitimate client._

p = 10−3 gives m ≈ 2.88 Mbit ≈ **360 KB** and k ≈ 10 hash functions. The asymmetry is the point: a Bloom filter has no false negatives, so it never lets a replay through; its error is the safe error.

### How many times can one flight run?

replays ≤ Ninstances   (each keeps its own cache)     replays = 1   (one authority per ticket)

  _→ in plain terms: RFC 8446 §8 says the MUST-level guarantee is “at most once per server instance”, which “limits the number of replays to the number of server instances”._

Accepts per second λ 10000 

Window W (± seconds) 10 

Server instances N 8

## §7 · Why it works: The attacker can only duplicate, never read or change

**The core insight:** the attacker can’t read, change or forge early data; they can only *duplicate* it. The binder authenticates the ClientHello, and the early key is derived from the ClientHello’s hash, so any edit changes the key and breaks decryption. So all of the security of 0-RTT reduces to one question: **is this request safe to run twice?** That is a question the application can answer and TLS cannot.

**Ablation: remove each piece.**

- **No replay cache:** every copy of the flight passes until the ticket expires (up to 7 days) or, if freshness is on, until the window closes. Freshness alone only *limits when* a replay can happen; it does not limit *how many* times.

- **No freshness check:** the cache must remember every ClientHello forever. Memory is unbounded; the check is what turns “remember everything” into “remember the last 20 s”.

- **No age obfuscation:** the age field becomes a stable identifier, letting a passive observer link connections that reuse a ticket.

- **No binder:** an attacker could splice a captured ticket into a different ClientHello of their choosing.

- **No “reject” option:** every server with imperfect state would have to take the replay risk or break the client; the escape hatch is what makes deployment survivable.

- **No application rule (“only send replay-safe data”):** everything above still leaves up to N runs per flight. RFC 8446 §8 puts it bluntly: clients “MUST only send early data which they deem safe to be replayed.”

## §8 · Knobs and alternatives: Window, lifetime and replay store: each trades memory for replay risk

| Knob | Tighter | Looser |

| Ticket lifetime (≤ 7 days, RFC) | Short: smaller replay and theft horizon | Long: more resumptions succeed; with no cache, a longer replay horizon |

| max_early_data_size | Small: less to replay, less to buffer | Large: bigger requests fit, bigger blast radius per replay |

| Acceptance window W (~10 s) | Small: smaller cache, more legit clients rejected (jitter, retransmits) | Large: bigger cache, wider replay window |

| Replay store | Single-use ticket DB (strict, stateful) · one owner zone per ticket (strong) | Per-zone caches (once per zone) · per-node (once per node) · none |

| Which requests may be early | GET/HEAD/OPTIONS only; Early-Data header; 425 for the rest | Anything (the client alone decides) |

| Ticket-key (STEK) rotation | Frequent: limits who can decrypt recorded early data later | Rare: weaker secrecy of recorded early data |

### Alternatives

- **Don’t use 0-RTT.** TLS 1.3 resumption is already 1-RTT, so the usual alternative costs one extra round trip.

- **TCP Fast Open** also carries data before the handshake completes, so applications there face an analogous duplicate-delivery caveat (not researched in depth here).

- **QUIC 0-RTT** is this mechanism, with the same trade-offs and the same RFC 8446 defenses (RFC 9001 §9.2).

- **Application-level idempotency keys** (a unique ID per operation that the server dedupes) remove the problem at the layer that can actually solve it, whatever the transport does.

**Why 0-RTT won where it won:** reads from a CDN edge are idempotent and plentiful, and latency to first byte is what users feel. For payments, nobody trades a round trip for a double charge.

## §9 · Where it breaks: Replays, retries and forward secrecy are three different failures

### Failure modes

- **Replayed state-changing requests.** The headline failure: a charge, an order or a vote runs once per replay that gets through.

- **“Idempotent” methods that aren’t.** A GET that bumps a counter, logs out, or triggers an action is safe in the HTTP spec and unsafe here. [Trail of Bits](https://blog.trailofbits.com/2019/03/25/what-application-developers-need-to-know-about-tls-early-data-0rtt/) makes the point that a “GET only” rule is not enough if your app uses GET for actions.

- **Retries, not replays.** A network attacker can drop the server’s answer so that the *client* retries on its own. RFC 8446 §8 says this second class “cannot be prevented at the TLS layer and MUST be dealt with by any application”, and that any app with client retries already needs its own defense.

- **Zones that don’t share state.** The RFC’s own example: duplicate the ClientHello to zone A and zone B. A accepts; B rejects and forces a full handshake; if the attacker blocks A’s reply, the client completes with B and retries, duplicating the request on the system as a whole.

- **No forward secrecy for early data.** The key comes from the PSK. If the ticket-encryption key (STEK) is later compromised, recorded early data can be decrypted. Tim Taubert’s 2017 write-up reported that Apache, nginx and HAProxy of the time did not rotate ticket keys automatically; I did not re-check current defaults.

- **Restarts.** A freshly started server’s replay window is empty. RFC 8446 §8.2: it SHOULD reject 0-RTT while any part of its recording window overlaps its startup time.

- **Clock tricks.** A ClientHello from a fast client clock can land “in the future”, be accepted for 1-RTT, trigger a client retry, and then be acceptable later for 0-RTT (an RFC 8446 §8.2 note).

- **Resource attacks.** Even idempotent requests can be abused by massive replay (timing, resource exhaustion; RFC 8446 Appendix E.5), hence the “at most once per instance” floor.

*(Figure: The same captured flight replayed at three cluster designs: runs once per node, once per zone, or once overall.)*
**Misconception:** “TLS 1.3 prevents replays.” It does for 1-RTT data. For early data the RFC says the opposite: “TLS does not provide inherent replay protections for 0-RTT data.”

**Misconception:** “The freshness window stops replays.” It only narrows *when* a replay can succeed; a copy sent a second later is still inside ±10 s.

**Misconception:** “A Bloom filter false positive breaks the connection.” RFC 8446 §8.2: it MUST reject 0-RTT but MUST NOT abort the handshake. The client just loses the round trip.

## §10 · In the wild: nginx off by default, QUIC requires it, Go’s TCP stack skips it

- **nginx**: `ssl_early_data` is off by default (since 1.15.3). `$ssl_early_data` is `"1"` during early data and empty after the handshake. The docs add that OpenSSL’s built-in anti-replay is off by default because it breaks resumption; opt in with `ssl_conf_command Options AntiReplay;`. An open bug report (nginx issue #1536) says a server-level `on` can be ignored when the http block disables it; I did not confirm whether the fix (PR #1557) has merged.

- **HTTP semantics**: RFC 8470 says a server that cannot safely process a request MUST answer `425`; intermediaries MUST set `Early-Data: 1` when forwarding an early-data request; clients MUST retry on 425 and retries MUST NOT be early data; 425 is not cacheable by default.

- **QUIC**: RFC 9001 §9.2 requires the RFC 8446 replay protections and notes they are imperfect; accepting 0-RTT “incurs a higher cost”; rejection is an `EncryptedExtensions` without `early_data`.

- **Cloudflare** (second-hand, see §1b): early-data limited to safe methods by its docs, an `Early-Data`-style signal to the origin, and a unique-value header so origins can dedupe non-idempotent endpoints against shared state, per Trail of Bits.

- **Go**: the stdlib TCP stack has no early-data toggle; the QUIC side has its own session-ticket early-data option (name per a search snippet, unverified).

- **Multi-server reality**: an upgrade of the terminating software can silently turn the feature on; operators rarely know whether replay state is shared across their fleet.

**Deviation from the textbook:** the RFC’s ideal is “accept at most once”. Real deployments commonly accept “at most once per node or zone” and push the rest to the app via headers and 425.

## §11 · Frontier: Replay handling is settled; post-quantum tickets are the live edge

**Honest status:** the replay story is mostly settled at the spec level (RFC 8446, 2018) and the HTTP and QUIC layers (RFC 8470, RFC 9001). My research found **one verified 2026 paper**, and the rest of the recent leads I could not open. I list those as leads, not facts.

| Year · Venue | Work | Contribution |

| 2026 · Frontiers in Computer Science 8 | HQRT: Hybrid Quantum-Resistant Resumption for zero-RTT TLS 1.3 (Abdul, Kondapalli) | Adds a hybrid X25519 + ML-KEM-768 encapsulation to ticket issuance so tickets and early data resist harvest-now-decrypt-later. Page fetched; the ticket-size numbers I saw only in a search snippet, so I do not quote them. |

| 2019 · ePrint 2019/228 | Session Resumption Protocols and Efficient Forward Security for TLS 1.3 0-RTT (Aviram, Gellert, Jager) | A puncturable-PRF construction that lets one server give early data forward secrecy without client changes. |

| 2017 · EuroS&P | Replay Attacks on Zero Round-Trip Time (Fischlin, Günther) | Shows 0-RTT replay affects key secrecy and analyses the PSK and (EC)DHE 0-RTT draft modes. |

| 2017 · IEEE S&P · CCS | Verified models for TLS 1.3 (Bhargavan, Blanchet, Kobeissi) · Comprehensive symbolic analysis | Machine-checked models; show a 0-RTT flight can be replayed and processed multiple times. |

| 2016 · IEEE S&P | Cremers, Horvat, Scott, van der Merwe: automated analysis of TLS 1.3 0-RTT | Tamarin model of draft-10 including resumption and 0-RTT. |

**Where the work moved.** Away from “how do we stop a replay” and toward (a) *post-quantum* resumption (the 2026 paper above) and (b) *multi-server* replay state. For (b) I found candidate papers (a ScienceDirect article “TLS Guard” and an IEEE survey on 0-RTT replay countermeasures, both around 2023) but could not open either, so their authors, venues and claims are unverified and I rely on neither. I also did not check whether the TLS working group’s `rfc8446bis` draft changes the anti-replay text.

## §11b · Open problems: Who tells the application the request is early?

- **Who tells the application?** The signal (`Early-Data: 1`) is advisory: the origin has to check it, and intermediaries have to set it. If any hop forgets, replay protection silently vanishes. Whether safety should instead be *opt-in by the app* is still debated in standards discussion (see the httpbis replay work).

- **Is shared replay state worth it?** Global consistent state across regions costs latency, which is the very thing 0-RTT was meant to save. The alternatives are “one owner zone per ticket” (needs routing) or “reject early data except for pure reads”. I found no measurement of how many real deployments have any shared state.

- **Forward-secure 0-RTT.** Puncturable constructions (2019) exist on paper. I found no evidence of mainstream deployment and did not look for it exhaustively.

- **Post-quantum tickets.** Hybrid ML-KEM tickets promise secrecy against harvest-now-decrypt-later but make tickets larger; how that interacts with anti-replay storage and QUIC’s amplification limits is not settled in anything I could verify.

- **Delay vs replay.** The freshness window does not stop an attacker from holding a flight for several seconds and then releasing it. One participant in an IETF thread argued this is a retry-style attack, not a replay; it was a hypothetical, not a reported incident.

I found **no** public production incident from a CDN where a non-idempotent request was replayed through 0-RTT. That could mean it hasn’t happened, or that nobody wrote it up.

## §12 · Lineage: From TLS 1.2 tickets and Google QUIC to RFC 8446’s one surviving 0-RTT mode

- **TLS 1.2 session tickets** (RFC 5077, 2008): stateless resumption, but the first request still waits a round trip.

- **Google QUIC** (designed ~2013): sent a request in the first packet by caching server config; replay was an accepted trade-off.

- **OPTLS** (Krawczyk & Wee, 2015, [ePrint 2015/978](https://eprint.iacr.org/2015/978.pdf)): the design background for 0-RTT with forward-secrecy goals in TLS 1.3.

- **TLS 1.3 drafts 2015–2017**: a (EC)DHE-based 0-RTT mode and a PSK-based 0-RTT mode were analysed (Fischlin & Günther, 2017, draft-12 and draft-14). The final standard keeps only PSK-based 0-RTT.

- **RFC 8446** (2018): early_data, the three anti-replay mechanisms in §8, the “clients MUST only send replay-safe early data” rule.

- **RFC 8470** (2018): `Early-Data` header and `425 Too Early`. **RFC 9001** (2021): QUIC inherits it.

- **2019 → 2026**: forward-secure 0-RTT constructions, then post-quantum resumption.

## §13 · Hands-on: Count how many times one captured flight can run

`sim.py` (in this folder, standard library only) models one captured 0-RTT flight replayed against a cluster, with the ticket-age arithmetic from §6 and different replay-cache layouts.

```
python3 sim.py            # 8 servers, ±10 s window, 50 replay attempts
python3 sim.py 16 5 200   # servers, window seconds, attempts
```

```
8 servers, window +/-10s, 50 replay attempts, replay arrives 1 s after the original

no replay protection at all                    runs of one request: 51
freshness window only                          runs of one request: 51
freshness + one cache per server               runs of one request: 8
freshness + one shared cache                   runs of one request: 1
freshness + cache, replay after window closes  runs of one request: 1
```

- Freshness alone does nothing against a prompt replay: 51 runs.

- Per-server caches cap it at the number of servers: 8. Your fleet size is your replay count.

- A shared cache gives 1, and a late replay (after the window) is refused by the age check without touching the cache.

### On the wire (optional)

Against a server you control with `ssl_early_data on`, OpenSSL’s client can send early data. The flags below exist in OpenSSL 3.6 (`s_client -help`), but I did not run this against a live server here:

```
openssl s_client -connect host:443 -tls1_3 -sess_out sess.pem  req.txt
openssl s_client -connect host:443 -tls1_3 -sess_in sess.pem -early_data req.txt
```

Watch for `Early data was accepted` or `rejected`. Run the second command twice quickly and see whether the server’s replay protection refuses the repeat.

## §14 · Question ladder: Test yourself

1. **Mechanism** · What exactly does the server compute from `obfuscated_ticket_age`, and what does it compare the result with?
   <details><summary>Answer</summary>It subtracts its stored `ticket_age_add` mod 2³² to get the client’s view of the ticket age, adds that to the ticket’s creation time (plus an RTT estimate) to predict when the ClientHello should arrive, and compares that with its own clock. Outside about ±10 s it rejects 0-RTT.</details>

2. **Mechanism** · Which two inputs does `client_early_traffic_secret` depend on?
   <details><summary>Answer</summary>The PSK (through the Early Secret) and the ClientHello transcript hash: `Derive-Secret(Early Secret, "c e traffic", ClientHello)`. No server input, which is why the data can be sent before the server speaks.</details>

3. **Mechanism** · The server rejects early data. What does it do with the records already on the wire?
   <details><summary>Answer</summary>It skips them: it tries to deprotect incoming records with the handshake key, discards the ones that fail (up to `max_early_data_size`), and treats the first one that succeeds as the client’s second flight. With a HelloRetryRequest it skips all application_data records instead.</details>

4. **Mechanism** · What does the PSK binder cover, and why must `pre_shared_key` be the last extension?
   <details><summary>Answer</summary>The binder is an HMAC over the ClientHello up to (not including) the binders, keyed by the PSK. The extension must be last so everything that precedes it is covered by the binder computation.</details>

5. **Why** · Why add `ticket_age_add` to the age?
   <details><summary>Answer</summary>Without it the age is a stable number an observer could use to link connections that reuse a ticket. The random per-ticket offset hides it from everyone except the server that chose it.</details>

6. **Why** · Why must a Bloom-filter replay store reject 0-RTT on a hit instead of aborting?
   <details><summary>Answer</summary>A false positive would otherwise kill a legitimate connection. Rejecting only costs the client the round trip, and a Bloom filter has no false negatives, so it never lets a replay through.</details>

7. **Why** · Why can’t TLS prevent the client-retry class of attack?
   <details><summary>Answer</summary>The server sees two separate, legitimately encrypted requests from a client that thinks the first one failed. Nothing at the TLS layer links them, so the application must dedupe.</details>

8. **Why** · Why is early data not forward secret when 1-RTT data is?
   <details><summary>Answer</summary>1-RTT keys mix in a fresh ephemeral (EC)DHE secret that is deleted afterwards. Early keys come only from the PSK, so whoever later obtains the ticket-encryption key or PSK can decrypt recorded early data.</details>

9. **Counterfactual** · Keep the ClientHello cache but remove the freshness check. What breaks?
   <details><summary>Answer</summary>The cache must now remember every ClientHello forever, because any old flight could be replayed. Freshness is what lets entries expire after ~2W.</details>

10. **Counterfactual** · If the server mixed fresh randomness into the early key, what would it cost?
   <details><summary>Answer</summary>The client would have to wait for the server’s share, which is exactly the round trip 0-RTT saves, and the first-flight data could no longer be encrypted.</details>

11. **Counterfactual** · What if all 8 nodes shared ticket keys but nobody shared caches, versus sharding tickets by hash to one owner node?
   <details><summary>Answer</summary>Shared keys alone let every node decrypt the ticket, so each accepts once: up to 8 runs. Routing each ticket to one owner that alone accepts 0-RTT, and rejecting elsewhere, gives 1.</details>

12. **Counterfactual** · What if ticket lifetime were 30 seconds?
   <details><summary>Answer</summary>The replay horizon and theft horizon shrink dramatically, but few clients would hold a valid ticket when they return, so most resumptions (and so most 0-RTT) would disappear.</details>

13. **Adversarial** · You sit on the café wifi. How do you make the app charge twice, and what stops you?
   <details><summary>Answer</summary>Record the first flight of a `POST /pay` sent as early data and resend it. A replay cache catches repeats on that server, but the real stops are: the client must not send non-idempotent requests early, and the server must answer 425 for early-data requests it can’t safely repeat.</details>

14. **Adversarial** · You delay a flight by 8 s instead of copying it. Why does the freshness check let it through, and is it harmful?
   <details><summary>Answer</summary>The age check passes inside ±10 s. It is not a duplicate, so the cache won’t flag it; it is a delay attack on a request that is still valid. Whether that matters depends on the request’s time sensitivity.</details>

15. **Adversarial** · How does stealing the ticket-encryption key (STEK) change the threat?
   <details><summary>Answer</summary>The attacker can decrypt every ticket they recorded, recover the PSKs, and decrypt any recorded early data, and can mint tickets. Early data has no forward secrecy against this.</details>

16. **Connection** · How do HTTP idempotency and the 425 status relate?
   <details><summary>Answer</summary>The origin uses `Early-Data: 1` to know the request arrived early; for non-idempotent ones it answers 425, which tells the client to retry after the handshake (not as early data).</details>

17. **Connection** · How is QUIC 0-RTT different from TLS-over-TCP 0-RTT?
   <details><summary>Answer</summary>It is the same TLS mechanism carried in QUIC packets; QUIC omits `EndOfEarlyData`, rejection shows up as an EncryptedExtensions without `early_data`, and RFC 9001 §9.2 says the replay protections are mandatory but imperfect.</details>

18. **Connection** · How does an application-level idempotency key relate to 0-RTT replay defenses?
   <details><summary>Answer</summary>Both turn “run twice” into “run once”, but the key does it at the layer that knows what the operation means, so it works for retries, replays and every transport.</details>

19. **Open** · Should CDNs enable 0-RTT by default?
   <details><summary>Answer</summary>Contested: the win is real for reads, the risk is concentrated in origins that never learn the request was early. No consensus from what I could verify.</details>

20. **Open** · How would you measure how many deployments share replay state?
   <details><summary>Answer</summary>Nobody I found has published such a measurement. You would need active probing: replay one captured flight to many addresses of the same service and count how many accept it.</details>


## §15 · Go deeper next: Three topics that build on this

- **Ticket-key (STEK) rotation and the forward secrecy of resumption**: how long recorded sessions stay decryptable.

- **QUIC connection setup**: address validation, amplification limits and how 0-RTT fits (RFC 9000/9001).

- **Idempotency keys in API design**: making “run twice” safe at the application layer.

## Sources: Standards, papers, docs, and leads I could not open

### Standards

- [RFC 8446, TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446) (§2.3, §4.2.10, §4.2.11, §4.6.1, §7.1, §8, App. E.5)

- [RFC 8470, Using Early Data in HTTP](https://www.rfc-editor.org/rfc/rfc8470)

- [RFC 9001 §9.2, Using TLS to secure QUIC: replay attacks](https://www.rfc-editor.org/rfc/rfc9001#section-9.2)

### Papers

- [Fischlin & Günther, Replay Attacks on Zero Round-Trip Time, EuroS&P 2017](https://eprint.iacr.org/2017/082)

- [Dowling, Fischlin, Günther, Stebila, TLS 1.3 handshake analysis, CCS 2015](https://eprint.iacr.org/2015/914)

- [Krawczyk & Wee, OPTLS](https://eprint.iacr.org/2015/978.pdf)

- [Aviram, Gellert, Jager, Session Resumption Protocols and Efficient Forward Security for TLS 1.3 0-RTT](https://eprint.iacr.org/2019/228)

- [Cremers et al., Automated Analysis of TLS 1.3, S&P 2016](https://people.cispa.io/cas.cremers/downloads/papers/CHSV2016-TLS13.pdf)

- [Bhargavan, Blanchet, Kobeissi, Verified Models for TLS 1.3, S&P 2017](https://bblanche.gitlabpages.inria.fr/publications/BhargavanBlanchetKobeissiSP2017.pdf)

- [Abdul & Kondapalli, HQRT, Frontiers in Computer Science 2026](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2026.1848687/full)

### Code, docs, articles

- [nginx ngx_http_ssl_module (ssl_early_data, $ssl_early_data)](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)

- [Go crypto/tls Config](https://pkg.go.dev/crypto/tls)

- [Trail of Bits, What application developers need to know about TLS early data](https://blog.trailofbits.com/2019/03/25/what-application-developers-need-to-know-about-tls-early-data-0rtt/)

- [Tim Taubert, The future of session resumption](https://timtaubert.de/blog/2017/02/the-future-of-session-resumption)

- [Cloudflare, Introducing Zero Round Trip Time Resumption (0-RTT)](https://blog.cloudflare.com/introducing-0-rtt/) (not read in full)

- [Cloudflare docs, 0-RTT connection resumption](https://developers.cloudflare.com/speed/optimization/protocol/0-rtt-connection-resumption/) (summary only)

### Leads I could not open (not relied on)

- ScienceDirect “TLS Guard” article (pii S1319157823003518), IEEE document 10278190, `draft-ietf-tls-rfc8446bis` revision status.
