# ML-KEM (Kyber): noisy lattices, the FO transform, and why the bugs are always in the implementation

**Cryptography · ML-KEM / FIPS 203: Module-LWE, the incomplete NTT, Fujisaki–Okamoto with implicit rejection, KyberSlash / Clangover / binding · hard · 2026-10-03**

> More than half of human web traffic to Cloudflare now runs a key exchange whose security comes from a 256-coefficient polynomial being deliberately *wrong* by about ±76. This dive shows how that works, why it is decrypted correctly anyway (with failure probability 2^-164.8, which you can reproduce in this folder), and why every practical break so far went through the code rather than the math.

---

## 0b. Plain English first

### Explain it simply

Two computers that have never met want to agree on a secret key while everyone on the network listens. For decades they did this with a trick (Diffie–Hellman) that a large quantum computer could undo. People are recording encrypted traffic today in case they can decrypt it later, so the replacement has to be in place before such a machine exists.

ML-KEM works like a **locked box mailed in one direction**. You publish an open box with a special lock. I put a random 32-byte note inside, snap it shut and mail it back. Only you can open it, and we both turn the note into the session key. The odd part is how the lock works. Imagine a clock face with 3,329 ticks instead of 12. To write one bit of the note I set a hand to **12 o'clock for 0 or 6 o'clock for 1**, then bump it by a few hundred random ticks of "smudge", which hides it from eavesdroppers. You hold a secret that removes most of the smudge, though not all of it. What remains is still small enough that you can see whether the hand is nearer 12 or 6, and you round it. The scheme is tuned so the remaining smudge almost never pushes a hand past 3 or 9 o'clock. The chance of that happening is lower than guessing a 160-bit number.

There is one more safety step. Once you have read my note, you **rebuild the box yourself** from the note, the same way I built it, and check it matches what arrived byte for byte. If it doesn't, someone tampered with it. You don't announce that. You quietly use a nonsense key, so the tamperer learns nothing from your reaction.

### Everyday example

Your laptop opens your bank's website.

1. The laptop invents a fresh lock and sends the open box (1,184 bytes) inside its first "hello" message.
2. The bank's server picks 32 random bytes as the note. It writes each of the 256 bits as a smudged clock hand and seals them into a reply box (1,088 bytes).
3. The laptop removes its share of the smudge. The first eight hands come out at ticks 1666, 95, 1647, 3318, 3290, 1760, 3208 and 1781. Near 6 o'clock (1665) reads as 1; near 12 o'clock (0 or 3329) reads as 0. That gives 1, 0, 1, 0, 0, 1, 0, 1, which is exactly what the server wrote. The worst leftover smudge in this run was 121 ticks, and it would take 832 to cause a mistake.
4. The laptop re-seals the note into a box of its own. It is identical to the one that arrived, so the laptop trusts it.
5. Both sides now hold the same 32-byte key, and the rest of the session is encrypted with it.

Someone who copied every byte of that exchange is left facing a "find the small smudge" puzzle in 768 dimensions. Nobody knows how to solve it, on a classical or a quantum computer.

**Now the same thing, technically.**

---

## 1. Bare-minimum context

- **KEM (key encapsulation mechanism)**: `KeyGen() → (ek, dk)`, `Encaps(ek) → (K, c)`, `Decaps(dk, c) → K`. It is not a two-sided DH exchange: only one party picks the secret. ([FIPS 203 §3](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf))
- **LWE (Learning With Errors)**: given A and b = As + e with s and e small, finding s is believed hard even for quantum computers. Remove the e and Gaussian elimination solves it. ([Regev 2005](https://cims.nyu.edu/~regev/papers/qcrypto.pdf))
- **Polynomial ring R_q = Z_q[X]/(X^256+1)**: vectors of 256 integers mod q, multiplied as polynomials where X^256 wraps to −1 (a negacyclic convolution).
- **NTT (number-theoretic transform)**: an FFT over Z_q. It turns that convolution into pointwise products. ([FIPS 203 §4.3](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf))
- **IND-CPA vs IND-CCA2**: IND-CPA means secure against eavesdroppers. IND-CCA2 means secure against someone who can submit ciphertexts of their choice and watch the result. Reusable keys need CCA2.
- **Random oracle model (ROM/QROM)**: proofs treat hash functions as ideal random functions. The QROM version lets a quantum attacker query them in superposition.

## 1b. Real-world context

### What it is, in one paragraph
ML-KEM (Module-Lattice-based Key-Encapsulation Mechanism) is NIST's standardized post-quantum KEM, published as **FIPS 203 on Aug 13, 2024**. It is CRYSTALS-Kyber with some changes. It has three parameter sets, ML-KEM-512, -768 and -1024, targeting NIST security categories 1, 3 and 5 (equivalent to AES-128, -192 and -256). NIST recommends **ML-KEM-768 as the default**. One party sends an encapsulation key, the other sends a ciphertext, and both end up with a 32-byte shared secret. Its security rests on the **Module-LWE** problem.

### Why it exists
- **Shor's algorithm** breaks RSA, finite-field DH and elliptic-curve DH in polynomial time on a large enough quantum computer.
- **Harvest-now-decrypt-later** means that key exchange performed today is already exposed if the recorded traffic still matters in 10–20 years. Authentication can wait until a quantum computer exists; confidentiality cannot. That is why KEMs are being migrated first and signatures (ML-DSA) lag behind.
- **NIST ran a competition**: call for proposals Dec 2016, 69 round-1 submissions, Kyber selected Jul 5 2022, FIPS 203 published Aug 13 2024. HQC was added as a code-based backup on Mar 11 2025. ([NIST timeline](https://csrc.nist.gov/projects/post-quantum-cryptography/workshops-and-timeline))
- **Why Kyber won**: it is very fast (often faster than X25519 in CPU time) and its keys and ciphertexts are around 1 KB. Classic McEliece needs about 261 KB public keys and FrodoKEM about 15.6 KB.

### Where it's used

| System | Role |
|---|---|
| **TLS 1.3 / Chrome, Firefox, Safari** | Hybrid group `X25519MLKEM768` (codepoint 0x11EC). On by default since Chrome 131 (Nov 2024), Firefox 132 and Apple OS 26 (Sep 2025). It replaced the draft `X25519Kyber768Draft00` (0x6399, Chrome 124) ([Google](https://security.googleblog.com/2024/09/a-new-path-for-kyber-on-web.html), [Cloudflare](https://blog.cloudflare.com/pq-2025/)) |
| **Cloudflare edge** | More than 50% of human traffic used PQ key agreement by Oct 2025 and more than 65% by Apr 2026. Origin support lags: about 10% of origins by Feb 2026 ([pq-2025](https://blog.cloudflare.com/pq-2025/), [roadmap](https://blog.cloudflare.com/post-quantum-roadmap/)) |
| **OpenSSH 10.0** | `mlkem768x25519-sha256` has been the default key exchange since Apr 2025. It replaced `sntrup761x25519`, the default since 9.0 in 2022. Uses libcrux's formally verified C ([release notes](https://www.openssh.com/txt/release-10.0)) |
| **Signal** | PQXDH (Sep 2023) adds Kyber to X3DH. SPQR / Triple Ratchet (Oct 2025) runs an ML-KEM-768 "Braid" ratchet that sends erasure-coded chunks of keys and ciphertexts on ordinary messages ([Signal](https://signal.org/blog/spqr/)) |
| **Apple iMessage PQ3** | Kyber-1024 for the initial key, Kyber-768 for rekeying about every 50 messages ([Apple](https://security.apple.com/blog/imessage-pq3/)) |
| **AWS KMS / ACM / Secrets Manager** | Hybrid PQ TLS through s2n-tls and AWS-LC, which uses the formally verified mlkem-native. Cost: about 1600 extra bytes and 80–150 µs per handshake ([AWS](https://aws.amazon.com/blogs/security/ml-kem-post-quantum-tls-now-supported-in-aws-kms-acm-and-secrets-manager/)) |
| **Go 1.24, OpenSSL 3.5, Java 24, Windows CNG** | Standard-library ML-KEM. Go and OpenSSL enable hybrid TLS by default ([Go 1.24](https://go.dev/doc/go1.24), [OpenSSL 3.5](https://openssl-library.org/news/openssl-3.5-notes), [JEP 496](https://openjdk.org/jeps/496)) |
| **Mullvad / Rosenpass (WireGuard)** | ML-KEM alongside Classic McEliece to derive WireGuard's pre-shared key ([Mullvad](https://mullvad.net/blog/quantum-resistant-tunnels-are-now-the-default-on-desktop)) |

### How it's used

Application code calls three functions. Go 1.24:

```go
import "crypto/mlkem"

dk, _ := mlkem.GenerateKey768()                // receiver
ekBytes := dk.EncapsulationKey().Bytes()        // 1184 B, send to peer

ek, _ := mlkem.NewEncapsulationKey768(ekBytes)  // sender (runs the modulus check)
ss, ct := ek.Encapsulate()                      // 32 B secret, 1088 B ciphertext; send ct

ss2, _ := dk.Decapsulate(ct)                    // receiver: ss2 == ss
seed := dk.Bytes()                              // 64-byte d||z: the recommended private-key format
```

OpenSSL 3.5+ CLI (in this folder I checked it interoperates byte for byte with `mlkem.py`):

```bash
openssl genpkey -algorithm ML-KEM-768 -out key.pem
openssl pkeyutl -encap -inkey key.pem -secret ss.bin -out ct.bin
openssl pkeyutl -decap -inkey key.pem -in ct.bin -secret ss2.bin
```

Typical integration is a **hybrid**: run X25519 and ML-KEM-768 side by side and feed both secrets to the KDF. TLS concatenates `ML-KEM ss ‖ X25519 ss` (64 bytes) into the key schedule. The client key share is 1216 bytes (1184 + 32) and the server share is 1120 bytes (1088 + 32). Clients usually send a plain X25519 share as well, so a server that doesn't support the hybrid doesn't force a HelloRetryRequest round trip.

### When to use it, and when not

| Use ML-KEM when | Skip it, or use something else, when |
|---|---|
| You need ephemeral key agreement in an interactive protocol (TLS, SSH, IKE, messaging handshakes) | You need **non-interactive** DH: static-static agreement, the DH ratchet, implicit authentication in Noise or WireGuard. A KEM can't do that. Redesign the protocol or look at lattice NIKEs like SWOOSH (about 220 KB keys) |
| The data must stay confidential for 10+ years | You need authentication. ML-KEM authenticates nobody. Use signatures (ML-DSA) or KEM-based authentication |
| Bandwidth is about 1 KB per side | Payloads must fit 100-byte radio frames. Consider Classic McEliece (tiny ciphertext, huge pre-distributed key) or chunking like Signal |
| You want a conservative choice: run it as a **hybrid** with X25519 | You distrust structured lattices: FrodoKEM (plain LWE) or HQC (codes), at 4–15 KB |

Signs you picked wrong: connections time out behind old middleboxes (ClientHello now spans two packets), or a protocol proof assumed "DH-like" properties that a KEM lacks.

### Who should care
- **Infra and backend**: TLS terminators, load balancers and proxies have to read multi-packet ClientHellos (see [tldr.fail](https://tldr.fail/)).
- **Security and crypto engineers**: side channels in decapsulation, binding, private-key formats.
- **Protocol designers**: KEM ≠ DH.
- **Compliance**: CNSA 2.0 wants ML-KEM-1024. BSI and ANSSI want hybrids.

---

## 2. The one-liner and what it hides

> "ML-KEM is a lattice-based KEM whose security comes from Module-LWE: a public key is As + e, and the small error e makes it hard to recover s."

What that sentence leaves out:
1. **The error that protects the secret also corrupts the message.** Why does decryption work anyway, and how was 2^-164.8 computed? (§6)
2. **The lattice core is only CPA-secure.** On its own it falls to chosen-ciphertext key recovery. The **Fujisaki–Okamoto** transform with *re-encryption* and *implicit rejection* fixes that, and it also makes every side channel in decryption a key-recovery oracle. (§5, §7, §9)
3. **The NTT is part of the format, not just an optimization.** The matrix A is sampled directly in the NTT domain, and q = 3329 was picked so a 7-layer *incomplete* NTT exists. (§5, §6)
4. **"Compression" removes ciphertext bits and adds noise on purpose.** The noise budget is shared between sampled noise and rounding noise. (§6, §8)
5. **The shared key doesn't commit to everything you would assume.** ML-KEM isn't MAL-BIND-K-CT (an attacker with a malicious key can make two ciphertexts give the same K), which is why hybrids hash the transcript. (§9, §11)

## 3. The problem

- **The quantum threat is a deadline.** Shor's algorithm turns every DH and RSA key exchange recorded today into plaintext once a cryptographically relevant quantum computer exists. Nobody knows when that will be, but migrating takes a decade.
- **Plain LWE is too big.** An unstructured LWE public key is an n×n matrix of numbers mod q. FrodoKEM-976 has about 15.6 KB keys and ciphertexts. Ring-LWE puts structure in A (a single polynomial stands for a 256×256 matrix) and shrinks that 256-fold, but ties security to one ring.
- **Module-LWE is the compromise.** A is a k×k matrix of ring elements, so you raise security by increasing k (2→3→4) without redesigning the arithmetic. The same NTT code and q serve every security level.
- **Constraints that set q.** With n = 256 the scheme carries one message bit per coefficient, so 32 bytes per polynomial. A fast NTT needs n | (q−1). The smaller primes that qualify, 257 and 769, leave too little room between the noise and q/4 for a failure rate low enough for CCA security. 3329 = 13·2^8 + 1 is the next one ([Kyber R3 spec §1.4](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf)).
- **What the CPA core alone allows.** A static key used with the bare K-PKE falls to **key-mismatch attacks** that need only a few hundred to a few thousand queries (Qin et al.; 78 queries plus 2^32 lattice work in [ePrint 2024/810](https://eprint.iacr.org/2024/810)). Ring-LWE key exchanges with reused keys were broken the same way back in [Fluhrer 2016](https://eprint.iacr.org/2016/085). CCA security isn't optional.

Resulting sizes (FIPS 203 Table 3):

| | ek | dk (expanded) | ciphertext | K | failure δ | classical core-SVP |
|---|---|---|---|---|---|---|
| ML-KEM-512 | 800 | 1632 | 768 | 32 | 2^-138.8 | 118 (112 without the LWR-style argument) |
| ML-KEM-768 | 1184 | 2400 | 1088 | 32 | 2^-164.8 | 183 |
| ML-KEM-1024 | 1568 | 3168 | 1568 | 32 | 2^-174.8 | 256 |

## 4. Mental model

**A noisy dial with a secret calibration.** Each coefficient is a dial with q = 3329 positions. The public key is a set of dials (t = As + e) that look random unless you know the small calibration s. To send a bit, the sender adds a random-looking combination of public dials (tᵀy) plus small noise, then turns the dial by half a revolution for a 1. The receiver can compute nearly the same random combination from the other half of the ciphertext (sᵀu). Subtracting it leaves "half a turn or none, plus a small wobble".

**Where the analogy breaks:**
- The wobble isn't independent per dial. It is a **sum of hundreds of products** of small secrets (eᵀy − sᵀe₁ …), which is why its distribution can be computed exactly and why failures are correlated with the secret (failure boosting, §9).
- The dial isn't read once. Under FO the receiver **re-runs the sender's entire computation**, so the security argument depends on determinism (r = G(m‖H(ek))), and so do the attacks.
- The "noise" partly comes from **deliberately throwing away low-order bits** (compression). That isn't random noise the sender chose. It is a deterministic rounding error that only behaves like noise.

## 5. The mechanism, traced

One ML-KEM-768 encapsulation and decapsulation, with fixed seeds `d = 00…00`, `z = 01…01`, `m = a5 00 … 00`. All numbers come from `trace.py` in this folder. The same implementation round-trips against OpenSSL 3.6.

```
 RECEIVER (KeyGen)                              SENDER (Encaps)
 d,z ← 32B random each
 (ρ,σ) = SHA3-512(d ‖ k)          ek (1184 B)
 Â     = SampleNTT(ρ‖j‖i)   ─────────────────────────▶  modulus check on ek
 s,e   ← CBD_η1(SHAKE256(σ‖N))                        m ← 32B random
 t̂     = Â∘NTT(s) + NTT(e)                            (K, r) = SHA3-512(m ‖ H(ek))
 ek = enc12(t̂) ‖ ρ                                    c = K-PKE.Encrypt(ek, m, r)
 dk = enc12(ŝ) ‖ ek ‖ H(ek) ‖ z     c (1088 B)
                                  ◀─────────────────────────  keeps K
 m' = K-PKE.Decrypt(ŝ, c)
 (K', r') = SHA3-512(m' ‖ H(ek))
 c' = K-PKE.Encrypt(ek, m', r')     ← re-encryption (the FO check)
 return  c' == c ? K' : SHAKE256(z ‖ c)   (constant-time select)
```

**Step 1: KeyGen expands the seed.** `(ρ, σ) = G(d ‖ 0x03)`. The `k` byte was added in the final FIPS so a seed can't be expanded under two parameter sets. ρ = `6d3ae406…`, σ = `47730327…`.

**Step 2: Matrix Â from ρ.** Each entry is SHAKE128(ρ‖j‖i), read in 12-bit chunks and kept if below 3329. 4096 − 3329 = 767, so about 18.7% of chunks are rejected. Â[0][0] begins `686, 85, 609, 2930`. These values are **already in the NTT domain**: nobody ever computes A in the coefficient domain. That is why FIPS 203 calls the NTT "integral" to the scheme.

**Step 3: Small secrets via the centered binomial distribution.** For η = 2, each coefficient is (b₀+b₁) − (b₂+b₃) over 4 pseudo-random bits, so it lies in {−2,…,2} with probabilities 1/16, 4/16, 6/16, 4/16, 1/16 and variance η/2 = 1. Here s[0] begins `1, 1, 0, 2, 0, 0, 0, 0` and e[0] begins `1, −1, 0, 2, 1, 2, 0, 0`. CBD replaced the discrete Gaussian because it needs only bit counting: no tables, no floating point, nothing to leak through timing.

**Step 4: t̂ = Â∘ŝ + ê, stored uncompressed.** t̂[0] begins `2597, 1940, 1400, 3176`. These look uniform, which is the MLWE assumption. ek = 3 × 384 bytes (256 coefficients × 12 bits) + 32-byte ρ = **1184 B**. dk = ŝ (1152) ‖ ek (1184) ‖ H(ek) (32) ‖ z (32) = **2400 B**. It can be regenerated from the **64-byte seed d‖z**, which is what RFC 9935 recommends storing.

**Step 5: Encaps derandomizes.** m = `a5 00…`. `(K, r) = G(m ‖ H(ek))`, with H(ek) = `07f81a8b…`, K = `23571523…`, r = `202f8989…`. **All** encryption randomness (y, e₁, e₂) is derived from r, so encryption is a deterministic function of (ek, m). That makes re-encryption possible.

**Step 6: K-PKE.Encrypt.**
```
y, e1 ← CBD_2 (3 polys each);  e2 ← CBD_2
u = NTT⁻¹(Âᵀ ∘ NTT(y)) + e1                    3 polys
v = NTT⁻¹(t̂ᵀ ∘ NTT(y)) + e2 + Decompress_1(m)  each bit → 0 or 1665
c1 = enc10(Compress_10(u))   3·256·10 bits = 960 B
c2 = enc4(Compress_4(v))       256·4 bits  = 128 B        → c = 1088 B
```
Compression keeps only the top 10 bits of each u coefficient and the top **4** bits of each v coefficient. Rounding v to 16 levels adds up to ±104 of error per coefficient, the largest single noise source (§6).

**Step 7: Decrypt.** w = v′ − NTT⁻¹(ŝᵀ ∘ NTT(u′)):

| coefficient | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| m bit | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 1 |
| w | 1666 | 95 | 1647 | 3318 | 3290 | 1760 | 3208 | 1781 |
| noise = w − 1665·bit (centered) | 1 | 95 | −18 | −11 | −39 | 95 | −121 | 116 |
| Compress_1(w) | **1** | **0** | **1** | **0** | **0** | **1** | **0** | **1** |

Compress_1 rounds 2w/q. It returns 1 when w lies in [833, 2496], within q/4 of 1665. The noise is about ±100, nowhere near 832.

**Step 8: FO re-encryption.** Derive (K′, r′) = G(m′ ‖ h) using the h = H(ek) **stored in dk**, re-run Encrypt, and compare all 1088 bytes. They match, so return K′ = K.

**Step 9: Tampered ciphertext.** Flip one bit of c[0]. Decrypt probably still returns the same m′ (the bit flipped a u coefficient by about 3, which is in the noise), but re-encryption gives the *original* c, so c′ ≠ c_tampered. Decaps returns K̄ = SHAKE256(z ‖ c_tampered) = `f595db36…`. No error is raised, and the output is deterministic and pseudorandom. This is **implicit rejection**.

Rejection is implicit because:
- An explicit "invalid ciphertext" error is a one-bit oracle. Key-recovery attacks (decryption-failure and plaintext-checking attacks) need about 10³–10⁴ such bits.
- Implicit rejection makes accept and reject look the same to anyone without z. The FIPS forbids exposing the reject flag at all.

## 6. The math

### 6.1 Why decryption works: the cancellation

Write ρ_d(x) = x − Decompress_d(Compress_d(x)) for the rounding error. Let c_u = −ρ_du(u) and c_v = −ρ_dv(v) be the errors compression adds. Then the receiver sees

u′ = Aᵀy + e₁ + c_u,  v′ = tᵀy + e₂ + ⌈q/2⌋·m + c_v,  with t = As + e.

Compute w = v′ − sᵀu′:

w = (As + e)ᵀy + e₂ + ⌈q/2⌋m + c_v − sᵀ(Aᵀy + e₁ + c_u)
  = **sᵀAᵀy** + eᵀy + e₂ + ⌈q/2⌋m + c_v − **sᵀAᵀy** − sᵀe₁ − sᵀc_u

→ in plain terms: the large, uniform-looking term sᵀAᵀy appears once from the sender's side and once from the receiver's side, so it **cancels exactly**. What remains is the message plus

  **n_total = eᵀy − sᵀ(e₁ + c_u) + e₂ + c_v**,

where every term is a product of small things or a bounded rounding error.

**Correctness condition:** ‖n_total‖_∞ < ⌈q/4⌋ = 832. Why q/4: the two symbols sit at 0 and q/2, and the decision boundary is halfway between them.

### 6.2 How big is the noise? (variance)

One coefficient of a product of two polynomials in Z_q[X]/(X^256+1) is a signed sum of 256 coefficient products. The wraparound X^256 = −1 only flips signs. A dot product over a rank-k module therefore sums **kn = 768** such products for ML-KEM-768.

- CBD_η variance is η/2, so 1 for η = 2.
- eᵀy: 768 products of two variance-1 variables, giving variance 768.
- sᵀ(e₁ + c_u): c_u is roughly uniform with width q/2^du = 3.25, so Var(c_u) ≈ 3.25²/12 = 0.88. Variance = 768·(1 + 0.88) ≈ 1444.
- e₂: 1.
- c_v: width q/2^dv = 208, so Var = 208²/12 ≈ **3608**.

  σ² ≈ 768 + 1444 + 1 + 3608 = 5821, **σ ≈ 76.3**

→ in plain terms: the typical leftover wobble is about ±76 out of 3329. Measured over 51,200 coefficients with `experiments.py`, σ = 76.6 and the worst value was 292. Most of the noise, **62% of the variance**, comes from rounding v down to 4 bits, not from the sampled secrets. Kyber deliberately spends the noise budget on compression, because every bit saved there makes the ciphertext smaller.

### 6.3 Why the failure rate isn't what a Gaussian predicts

The threshold is 832 / 76.3 ≈ 10.9σ. A Gaussian tail for each of 256 coefficients gives

  P_fail ≈ 256 · erfc(10.9/√2) ≈ **2^-81**.

FIPS 203 gives **2^-164.8**. Convolving the actual distributions exactly (`failure_prob.py`, the same method as the Kyber team's script) reproduces 2^-138.8, 2^-164.8 and 2^-174.8 for the three parameter sets.

The 84-bit gap comes from a **bounded** term: |c_v| ≤ 104 always. To fail, the unbounded part eᵀy − sᵀ(e₁+c_u) has to supply at least 832 − 104 = 728 on its own. That part has σ ≈ √2213 ≈ 47, so 728 is about 15.5σ, far deeper in the tail. Even that part is a sum of products of *bounded* variables, so its tail is lighter than Gaussian too. (The decomposition is my own explanation; the numbers are from the scripts.)

→ in plain terms: you can't estimate lattice-KEM failure rates with a CLT approximation. You have to convolve the real distributions.

### 6.4 Why δ must be about 2^-128 or lower: the CCA bound

In the classical ROM, the Kyber R3 spec (Theorem 2) gives

  Adv^{IND-CCA}_{ML-KEM} ≤ 2·Adv^{MLWE}_{k+1,k,η} + Adv^{PRF} + **4·q_RO·δ**

where q_RO is the number of hash queries. With q_RO = 2^64 and ML-KEM-768, 4·2^64·2^-164.8 = 2^-98.8, which is negligible. In the QROM the bound degrades to 4q_RO·√Adv^{MLWE} + 8q_RO²·δ. That square root is why QROM tightness is still open (§11b).

→ in plain terms: each hash query is a lottery ticket for finding a ciphertext that fails to decrypt, and a failure leaks information about s. δ has to be small enough that 2^64 tickets win nothing.

### 6.5 Why the NTT has this form

q − 1 = 3328 = 2^8 · 13, so Z_3329 contains 256th roots of unity (ζ = 17: 17^128 ≡ −1) but **no 512th roots**. A full negacyclic NTT for X^256 + 1 would need a 512th root. So the polynomial splits only into 128 quadratics:

  X^256 + 1 = ∏_{i=0}^{127} (X² − ζ^{2·BitRev₇(i)+1})

The NTT therefore has **7 layers instead of 8**, and "pointwise" multiplication is 128 products in Z_q[X]/(X² − γᵢ):

  (a₀ + a₁X)(b₀ + b₁X) = (a₀b₀ + a₁b₁γᵢ) + (a₀b₁ + a₁b₀)X

→ in plain terms: one of the smaller primes would allow a full NTT but has too little room for noise. 3329 gives up one butterfly layer in exchange for a small modulus whose coefficients fit in 12 bits, and products of two fit in 32-bit lanes.

**Cost.** Schoolbook ring multiplication takes 256² = 65,536 multiplications. With the NTT it is about 7·128 = 896 butterfly multiplications per transform plus 128 base multiplications of about 5 multiplications each. A matrix–vector product Âᵀŷ needs k² = 9 base multiplications and only k transforms each way, because the operands are kept in the NTT domain.

### 6.6 Compression, exactly

Compress_d(x) = ⌈(2^d / q)·x⌋ mod 2^d,  Decompress_d(y) = ⌈(q / 2^d)·y⌋

The round-trip error is nearly uniform on |·| ≤ ⌈q/2^{d+1}⌋: ±2 for d = 10, ±1 for d = 11, ±104 for d = 4, ±52 for d = 5. FIPS 203 says floating point **shall not** be used. The reference code computed ⌈2^d·x/q⌋ with a C `/` by q. That line was **KyberSlash** (§9).

## 7. Why it works

**Core insight:** the receiver doesn't undo the noise. It **cancels the large term** sᵀAᵀy algebraically and leaves noise that is a sum of products of small values. MLWE hides s because t = As + e looks uniform. Correctness only needs the *products* of small values to stay below q/4. Those two requirements push η in opposite directions, and k, η, du, dv are chosen at the point where both hold.

**Ablations: remove each piece and see what breaks.**

| Remove | What breaks |
|---|---|
| e (the error in t) | t = As is solvable by Gaussian elimination, so the key is recovered from ek alone |
| The FO transform (use K-PKE directly) | Static keys fall to key-mismatch or plaintext-checking attacks after a few hundred to a few thousand chosen ciphertexts |
| Re-encryption (decrypt and hash, no comparison) | Malformed ciphertexts are processed and their effect on m′ leaks s coefficient by coefficient. This is what a fault attack that skips the comparison achieves |
| Implicit rejection (return ⊥ instead) | Still IND-CCA in theory (FO^⊥ variants exist), but you get a clean oracle for any side-channel-assisted attack and worse QROM bounds. Implicit rejection also hides reject-path timing |
| H(ek) in G(m ‖ H(ek)) | Multi-target attacks: precomputed failing ciphertexts would work against every key at once. Hashing ek ties r to one key |
| Compression | Ciphertext grows from 1088 to 1536 B (3·384 + 384) with no security gain. Compression error is noise the design counts on |
| The k byte in G(d ‖ k) | The same seed at two parameter sets gives related keys, which complicates seed-only key storage |
| The modulus check on ek | Non-canonical ek (coefficient ≥ q) is interpreted differently by different implementations, so they derive different secrets. That is an interoperability and consistency gap |

## 8. Design knobs and alternatives

| Knob | Values | Increase it and… |
|---|---|---|
| k (module rank) | 2/3/4 | lattice dimension kn grows (512/768/1024) → security ↑, ek and ct grow by about 384 B per step, noise variance grows linearly |
| η₁ (secret / y noise) | 3/2/2 | hardness ↑, failure rate ↑. ML-KEM-512 uses η₁ = 3 because its smaller dimension needs more noise per coefficient |
| η₂ (e₁, e₂) | 2 | as above, smaller effect |
| du | 10/10/11 | ciphertext ↑, c_u noise ↓ |
| dv | 4/4/5 | ciphertext ↑ by 32 B per bit, c_v noise ↓ (the dominant term) |
| q, n | fixed 3329, 256 | not tunable: NTT and encoding are built around them |

Round-3 history ([R3 spec](https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf)): Kyber-512 moved η₁ from 2 to 3 and dv from 3 to 4. The ciphertext grew from 736 to 768 B in exchange for more security margin.

**Alternatives:**

| Scheme | Assumption | pk / ct | Why chosen / not chosen |
|---|---|---|---|
| **FrodoKEM** | plain LWE (no ring) | ≈15.6 KB / 15.6 KB (976) | Most conservative lattice option, recommended by BSI. 10–15× bigger |
| **NTRU / sntrup761** | NTRU, prime-degree ring | 1158 / 1039 B (from memory) | Avoids cyclotomic structure. OpenSSH's PQ default 2022–2025 |
| **HQC** | quasi-cyclic codes | 2241 / 4433 B (HQC-1) | NIST backup (Mar 2025), a different assumption family. Slower decaps (≈353k cycles) |
| **Classic McEliece** | Goppa codes (1978) | ≈261 KB / ≈96–208 B | Decades of cryptanalysis. Only for pre-distributed long-term keys |
| **Saber** | Module-LWR (rounding instead of noise) | similar to Kyber | Power-of-two q, no NTT. Lost to Kyber in round 3 |

Kyber won on balance: around 1 KB, CPU cost at or below X25519 (ML-KEM-768 AVX2 runs about 29k/30k/40k cycles for keygen/encaps/decaps on recent x86 ([arXiv 2404.13544](https://arxiv.org/pdf/2404.13544)); Cloudflare measured 29–45k ops/s against about 19k for X25519), and a single arithmetic core for every level.

## 9. Where it breaks

The math has held. Every practical key recovery so far came through **implementations** or **composition**, and the FO re-encryption step is what turns small leaks into full key recovery.

**KyberSlash 1 & 2 (Dec 2023 – Jan 2024; TCHES 2025, Best Paper).**
- The reference code computed `t = (((t << 1) + KYBER_Q/2)/KYBER_Q) & 1` in `poly_tomsg` (KyberSlash1, during decryption) and similar `/KYBER_Q` lines in `poly_compress`/`polyvec_compress` (KyberSlash2, during encryption, which decaps runs as re-encryption on the secret m′).
- Whether this leaks depends on the compiler and CPU. `gcc -Os` on x86 emits DIV, and on Raspberry Pi 2 it calls `__divsi3`, which branches on its input. DIV latency depends on the operands: on Zen 2 it is 1 cycle slower once the numerator reaches 8192.
- Chosen ciphertexts steer the secret numerator across those thresholds. KyberSlash2 recovered keys in minutes on a Cortex-M4; KyberSlash1 took hours on a Raspberry Pi 2.
- Found by Cryspen while writing verified Rust, and independently by Bernstein via SUPERCOP.
- The fix is a multiply-and-shift `t = ((t<<1)+1665)*80635 >> 28 & 1`. `experiments.py` checks it equals the division for all 3329 inputs.
- More than 15 libraries were patched (liboqs, AWS-LC, Botan, pqm4, PQClean, zig std, …). Never vulnerable: BoringSSL, Go's mlkem768, libjade, the pq-crystals AVX2 code.
- Follow-up: the multiply-and-shift fix still leaks through **power**, giving SPA-assisted key recovery in about 30 s on a Cortex-M4 ([ePrint 2024/2051](https://eprint.iacr.org/2024/2051)).
- Sources: [kyberslash.cr.yp.to](https://kyberslash.cr.yp.to/faq.html), [ePrint 2024/1049](https://eprint.iacr.org/2024/1049).

**Clangover (Jun 2024, CVE-2024-37880).**
- `poly_frommsg` used the branch-free idiom `mask = -((msg[i]>>j)&1)`. Clang 15–18 recognized that the value is 0 or 1 and compiled it into a branch on secret m′, at `-Os`, `-O1`, and `-O2/-O3` with `-fno-vectorize`.
- That gives a timing plaintext-checking oracle and ML-KEM-512 key recovery in 5–10 minutes.
- Fixed with an empty inline-asm value barrier. liboqs: CVE-2024-36405.
- Lesson: **constant-time C is not preserved by the compiler**.
- Source: [clangover](https://github.com/antoonpurnal/clangover).

**Re-encryption comparison oracles.**
- A `memcmp` that exits early in FO decaps leaks how many bytes matched. Guo–Johansson–Nilsson broke FrodoKEM with about 2^30 decapsulations this way ([CRYPTO 2020](https://eprint.iacr.org/2020/743)).
- Power and EM leakage from the SHA-3 calls during re-encryption is a generic plaintext-checking oracle ("Curse of Re-encryption", [TCHES 2022](https://eprint.iacr.org/2021/849)).
- Fault injection that skips one instruction in decoding recovered a Kyber512 key from about 6,500 faulty decapsulations ([Pessl–Prokop TCHES 2021](https://eprint.iacr.org/2021/064)).
- **2026 logic bug:** wolfSSL's AVX2 `mlkem_cmp_avx2` compared only 1536 of the 1568 ciphertext bytes of ML-KEM-1024, so tampering with the last 32 bytes skipped implicit rejection. That is a plaintext-checking oracle needing about 350 queries and no timing at all. Reported as CVE-2026-10097 ([OpenCVE](https://app.opencve.io/cve/CVE-2026-10097); I have only seen this in aggregator listings, not NVD).

**Side channels on protected code (2025).**
- Chosen-ciphertext power attacks recover keys even from **shuffled** implementations: about 1,072 queries with an MLP classifier ([ePrint 2025/1956](https://eprint.iacr.org/2025/1956)).
- Template attacks on base multiplication need at most 40 traces ([ePrint 2025/1577](https://eprint.iacr.org/2025/1577)).
- Masking has to cover compress/decompress, the hashes and the comparison, not only the NTT.

**Binding failures.**
- An expanded dk is (ŝ, ek, H(ek), z), and decaps doesn't check that these are consistent. With a malicious key you can make two different ciphertexts, or two public keys, decapsulate to the same K.
- So ML-KEM is **not MAL-BIND-K-CT / MAL-BIND-K-PK** ([Schmieg, ePrint 2024/523](https://eprint.iacr.org/2024/523); [Cremers–Dax–Medinger CCS 2024](https://eprint.iacr.org/2023/1933)). It is LEAK-BIND for honestly generated keys.
- Fixes: seed-only private keys (64 B d‖z, now RFC 9935's recommendation) and protocols that hash ct and pk into the final key.

**Conformance gaps.**
- Symbolic Software's 2026 "Crucible" suite found that pq-crystals ref, PQClean and pqcrypto skip the FIPS modulus check and accept coefficient 3329 ([blog](https://symbolic.software/blog/2026-03-23-crucible)).
- Bouncy Castle 1.80 accepted a 2399-byte dk.

**Deployment breakage.**
- The ClientHello with a hybrid share is larger than one MTU. Middleboxes and servers that call `read()` once and expect the whole ClientHello broke when Chrome 124 shipped Kyber ([tldr.fail](https://tldr.fail/)).
- Go keeps `GODEBUG=tlsmlkem=0` as an escape hatch.

> **Misconceptions**
> - *"Kyber is quantum-proof."* It rests on the *assumption* that MLWE is hard. In April 2024 Yilei Chen's claimed polynomial-time quantum LWE algorithm caused real alarm until a bug in Step 9 was found and the claim was withdrawn on Apr 18 ([ePrint 2024/555](https://eprint.iacr.org/2024/555)). That episode is the argument for hybrids.
> - *"ML-KEM is a drop-in replacement for DH."* A KEM isn't a NIKE. There is no static-static agreement, no DH ratchet and no implicit authentication. Signal, Noise, WireGuard and EDHOC need redesigns ([draft-sfluhrer-cfrg-ml-kem-security-considerations](https://datatracker.ietf.org/doc/html/draft-sfluhrer-cfrg-ml-kem-security-considerations-00)).
> - *"Decryption failures don't matter at 2^-139."* Failures are why the parameters look the way they do. Failure boosting means finding the first one makes the next ones much cheaper ([D'Anvers et al. 2020](https://eprint.iacr.org/2019/1399)).
> - *"You can use K-PKE if you're careful."* FIPS 203 says it "shall not be used as a stand-alone scheme". With reused keys it leaks s.
> - *"Round-3 Kyber == ML-KEM."* They aren't wire-compatible: the FO variant changed, H(m) was removed and domain separation was added. That is why TLS needed a new codepoint.

## 10. In the wild: how implementations deviate from the textbook

- **AVX2 / AVX-512 implementations** merge NTT layers, use signed **Montgomery** (R = 2^16, QINV = −3327) and **Barrett** (v = 20159) reduction with lazy reduction across layers, and vectorize rejection sampling. Seiler's AVX2 NTT made polynomial multiplication 6.3× faster ([ePrint 2018/039](https://eprint.iacr.org/2018/039)). The reference code stores zetas in Montgomery form, and the inverse NTT finishes with a scale of 1441 = mont²/128.
- **libcrux (Cryspen)**: Rust verified with hax→F* for panic freedom, functional correctness and secret independence. Extracted to C, it ships in **Firefox/NSS** and **OpenSSH**. It warns that compiled binaries aren't verified side-channel free. Its verification work found KyberSlash.
- **mlkem-native (PQ Code Package, AWS)**: C proven memory-safe and overflow-free with **CBMC**. AArch64 and x86-64 assembly proven correct and constant-time in **HOL Light**. AArch64 code superoptimized with **SLOTHY**, which sits outside the trusted computing base because the proofs don't depend on scheduling. Gives 2.0–2.4× over the reference code in AWS-LC. Default ML-KEM in liboqs 0.13+ ([repo](https://github.com/pq-code-package/mlkem-native), [Amazon Science](https://www.amazon.science/blog/verifying-and-optimizing-post-quantum-cryptography-at-amazon)).
- **Jasmin / libjade + EasyCrypt**: a machine-checked IND-CCA proof of ML-KEM linked to a constant-time x86 implementation that is about as fast as unverified AVX2 code ([CRYPTO 2024, ePrint 2024/843](https://eprint.iacr.org/2024/843)).
- **Go `crypto/mlkem`** (Filippo Valsorda): written from scratch against the spec, about 500 lines, specialized encoders for 1/4/10/12 bits, Barrett reduction without division, seed-only keys. Now inside the FIPS 140-3 Go module ([blog](https://words.filippo.io/mlkem768/)).
- **Private keys**: BoringSSL, Go and RFC 9935 recommend the **64-byte seed** over the 2400-byte expanded key. OpenSSL keeps both by default (`seed-priv`) because HSMs often only hold expanded keys.
- **TLS byte order**: X25519MLKEM768 puts **ML-KEM first** (`mlkem ‖ x25519`). The NIST-curve hybrids put ECDHE first. The draft codepoint 0x6399 used the opposite order.
- **Signal SPQR**: uses the fact that the 960-byte part of an ML-KEM-768 ciphertext depends only on ρ and the randomness, not on t, so the sender can start once a 64-byte header arrives. Keys and ciphertexts are erasure-coded into chunks (37 and 34) that ride on ordinary messages ([Signal](https://signal.org/blog/spqr/)).

## 11. Frontier (what's new, 2024–2026)

1. **KyberSlash**: Bernstein, Bhargavan, Bhasin, Chattopadhyay, Chia, Kannwischer, Kiefer, Paiva, Ravi, Tamvada. *TCHES 2025(2), CHES 2025 Best Paper.* Secret-dependent division timing in compress; practical key recovery; Valgrind patch scanning more than 1000 SUPERCOP implementations. [ePrint 2024/1049](https://eprint.iacr.org/2024/1049)
2. **Formally Verifying Kyber Episode V**: Almeida et al. *CRYPTO 2024.* Machine-checked IND-CCA security and correctness of ML-KEM in EasyCrypt, linked to a verified constant-time Jasmin implementation. [ePrint 2024/843](https://eprint.iacr.org/2024/843)
3. **Keeping Up with the KEMs**: Cremers, Dax, Medinger. *ACM CCS 2024.* Defines the X-BIND-P-Q binding notions, analyses KEM-based protocols automatically in Tamarin, and shows implicit rejection complicates MAL-binding. [ePrint 2023/1933](https://eprint.iacr.org/2023/1933). Companion: **Unbindable Kemmy Schmidt**, Schmieg 2024: ML-KEM is neither MAL-BIND-K-CT nor MAL-BIND-K-PK. [ePrint 2024/523](https://eprint.iacr.org/2024/523)
4. **X-Wing**: Barbosa, Connolly, Duarte, Kaiser, Schwabe, Varner, Westerbaan. *IACR CiC 1(1), 2024.* Hybrid KEM K = SHA3-256(label ‖ ss_M ‖ ss_X ‖ ct_X ‖ pk_X). It can leave ct_M and pk_M out of the hash because ML-KEM's binding of honest keys is proven. Shipped in Apple CryptoKit HPKE. [ePrint 2024/039](https://eprint.iacr.org/2024/039)
5. **Triple Ratchet / SPQR**: Dodis, Jost, Katsumata, Prest, Schmidt (and Auerbach). *Eurocrypt 2025 + USENIX Security 2025.* Bandwidth-efficient hybrid-secure Signal with an ML-KEM Braid and erasure-coded chunks. Deployed Oct 2025. [ePrint 2025/078](https://eprint.iacr.org/2025/078)
6. **Dual attacks on firmer ground**: Ducas–Pulles, "Does the Dual-Sieve Attack on LWE even Work?" (*CRYPTO 2023*, [2023/302](https://eprint.iacr.org/2023/302)) showed MATZOV-style estimates relied on a flawed independence heuristic. Since then: Pouly–Shen, provable dual attacks (*EUROCRYPT 2024*, [2023/1508](https://eprint.iacr.org/2023/1508)); Ducas–Pulles accurate score prediction (*J. Cryptology 2026*, [2023/1850](https://eprint.iacr.org/2023/1850)); a provable FFT dual attack on ML-KEM ([2026/2166](https://eprint.iacr.org/2026/2166); seen in search results only). No result puts ML-KEM below its claimed category.
7. **Side channels against protected code**: chosen-ciphertext attacks on shuffled Kyber, about 1,072 queries ([2025/1956](https://eprint.iacr.org/2025/1956)); SPA on the KyberSlash-patched code ([2024/2051](https://eprint.iacr.org/2024/2051)); an open EM dataset of 200k traces each for the reference, pqm4 and masked implementations ([2026/1851](https://eprint.iacr.org/2026/1851)).
8. **Standards and measurement**: NIST **SP 800-227** *Recommendations for KEMs* (final Sep 18 2025, [csrc](https://csrc.nist.gov/pubs/sp/800/227/final)); **RFC 9935** (ML-KEM in X.509, seed-preferred private keys); the TLS hybrid draft `draft-ietf-tls-ecdhe-mlkem` (one source says it was published as an RFC in Aug 2026, another lists it as draft -05 in May 2026; check the [datatracker](https://datatracker.ietf.org/doc/draft-ietf-tls-ecdhe-mlkem/)). Measurement: "Mind the Gap: Policy vs Reality in PQ TLS" (*IMC 2026*, [arXiv 2607.29005](https://arxiv.org/abs/2607.29005)) found that by March 2026 about half of a stable domain panel defaulted to PQ key exchange, almost all X25519MLKEM768, with deployment driven by CDNs rather than national roadmaps.

## 11b. Open problems

- **Concrete hardness of the parameters.** Do refined attacks push ML-KEM-512 below category 1? MATZOV (2022) lowered Kyber-512 to about 2^137.5 gates, against a 2^143 floor. NIST argued memory-access costs restore the margin. Bernstein (2023) argued NIST multiplied costs that should be added. Ducas–Pulles then questioned the dual-attack success estimates themselves. It is unsettled because "cost" depends on the model: gates, memory access (RAM vs. area-time) and quantum sieving speedups are all debated. In practice deployments chose 768 and CNSA 2.0 chose 1024.
- **Module structure.** Cramer–Ducas–Wesolowski (2017) showed quantum attacks on approx-SVP in *ideal* lattices of cyclotomic fields at large approximation factors. Nothing similar is known for *module* lattices at Kyber's parameters, but nobody can prove the module structure is harmless. Hedges: FrodoKEM (no structure) and HQC (different math).
- **Tight QROM proofs.** The QROM reduction loses a square root and a q_RO² factor. Tight bounds exist only under non-standard assumptions (pseudorandomness of deterministic K-PKE). Direct proofs for implicit-rejection FO (Barbosa–Hülsing [2023/755](https://eprint.iacr.org/2023/755)) improve on that but don't close the gap.
- **Constant-time all the way down.** Clangover showed compilers undo constant-time C. KyberSlash showed "obvious" arithmetic compiles to DIV. The SPA follow-up showed the fix still leaks power. Verified assembly (HOL Light, Jasmin) covers the instructions but not microarchitectural leakage such as variable-time multipliers or power. Hard because it needs leakage models of real silicon.
- **Masking cost.** First-order masking of decaps (A2B and B2A conversions around compress and the comparison) costs several times the unmasked runtime, and attacks on shuffled and masked code keep improving.
- **No lattice NIKE yet.** SWOOSH has about 220 KB keys. Protocols built on static DH (Noise IK, WireGuard, the DH ratchet) need either expensive NIKEs or redesigns around KEMs, each with its own proof.
- **Binding as the default.** Should future KEM APIs commit to (ct, pk) by default? X-Wing and the CFRG combiners do it in the hybrid layer. Plain ML-KEM leaves it to each protocol.
- **Authentication sizes.** ML-DSA signatures are 2.4–4.6 KB. A PQ-authenticated TLS chain adds about 15 KB against Chrome's 10% regression budget. Candidates: KEMTLS, Merkle tree certificates, trust-anchor negotiation.

## 12. Lineage

```
Ajtai 1996 (SIS, worst-case → average-case)
  └─ Regev 2005: LWE + public-key encryption
      ├─ Lyubashevsky–Peikert–Regev 2010: Ring-LWE  →  NewHope (2016, Chrome CECPQ1 experiment)
      ├─ Langlois–Stehlé 2012/15: Module-LWE
      │     └─ Bos et al. 2017/18 (EuroS&P): CRYSTALS-Kyber
      │           └─ NIST rounds 1–3 (2017–2020) → selected Jul 2022
      │                 └─ FIPS 203 ML-KEM (Aug 13 2024)
      │                       ├─ X25519MLKEM768 in TLS, OpenSSH 10, SPQR, PQ3
      │                       └─ X-Wing, CFRG hybrid combiners, SP 800-227 (2025)
      └─ Frodo (2016): plain LWE  →  FrodoKEM
Fujisaki–Okamoto 1999 → Hofheinz–Hövelmanns–Kiltz 2017 (modular FO, implicit rejection)
Hoffstein–Pipher–Silverman 1996: NTRU  →  NTRU Prime / sntrup761 (OpenSSH 2022)
```

## 13. Hands-on (≤30 min)

Everything is in this folder and needs only Python 3 (+ numpy for `failure_prob.py`).

```bash
python3 mlkem.py         # all 3 parameter sets: sizes + round-trip + implicit-rejection demo
python3 trace.py         # the section-5 trace with fixed seeds
python3 experiments.py   # noise histogram (σ≈76, worst ≈290 of 832), KyberSlash fix check, rejection
python3 failure_prob.py  # reproduces FIPS 203's 2^-138.8 / 2^-164.8 / 2^-174.8 vs Gaussian 2^-76/-81/-146
```

**Interoperability with OpenSSL 3.5+** (checked here with OpenSSL 3.6):

```bash
SEED=$(python3 -c "print(bytes(range(64)).hex())")
openssl genpkey -algorithm ML-KEM-768 -pkeyopt hexseed:$SEED -out k.pem
openssl pkey -in k.pem -pubout -outform DER -out pub.der
openssl pkeyutl -encap -inkey k.pem -secret ss.bin -out ct.bin
python3 -c "
import mlkem
ek, dk = mlkem.keygen('ML-KEM-768', bytes(range(32)), bytes(range(32,64)))
print('ek matches:', open('pub.der','rb').read().endswith(ek))
print('decaps matches:', mlkem.decaps(dk, open('ct.bin','rb').read()) == open('ss.bin','rb').read())"
```

**Things to try:**
1. Call `failure_prob.failure(3, 2, 2, 10, dv)` for dv = 3, 4, 5. Each bit of dv moves δ by tens of bits: 2^-123.5, 2^-164.8, 2^-187.0. At dv = 3 the Gaussian estimate says 2^-25, an even bigger gap, because the bounded c_v term (±208) now carries even more of the variance. Saving 32 bytes would cost about 41 bits of failure margin.
2. In `experiments.py`, log `w` for a ciphertext whose `c2` you corrupt by +1 in one 4-bit nibble. The coefficient moves by 208. Find how many such corruptions flip a bit.
3. Replace `ok = c == c2` in `decaps` with a byte loop that returns early, and time it with `time.perf_counter_ns` on flipped bytes at the start and at the end of c. This is the Guo–Johansson–Nilsson oracle in miniature. Python is far too noisy for a real attack, but the structure is the same.

## 14. Question ladder

### Mechanism
1. In w = v′ − sᵀu′, which term cancels, and why does the receiver need s and not e to cancel it?
2. Why is Â sampled directly in the NTT domain, and what would change if FIPS 203 sampled A in the coefficient domain?
3. Exactly which values in decapsulation depend on the secret, and which of them did KyberSlash1 and KyberSlash2 leak?
4. Why does Decaps use the H(ek) stored in dk rather than recomputing it, and what goes wrong if the stored value is inconsistent?
5. Walk through what happens to K when a single bit of c₂ is flipped.

### Why
6. Why q = 3329 and not 257 or 769, both of which also allow an NTT?
7. Why does dv = 4 dominate the noise, and why is that a deliberate choice?
8. Why does the Gaussian estimate (2^-81) disagree with the exact convolution (2^-164.8) by about 84 bits?
9. Why implicit rejection rather than returning an error?
10. Why does TLS still run X25519 alongside ML-KEM?

### Counterfactual
11. If ML-KEM skipped re-encryption and returned H(m′, c), what attack becomes practical?
12. If keys were only ever ephemeral (used once), which parts of ML-KEM could you drop, and why did NIST keep them anyway?
13. If n were 512 with k = 1 (Ring-LWE), what would you gain and lose?
14. What if the shared key were G(m ‖ H(ek)) without H(ek), as an attacker precomputing failures would like?

### Adversarial
15. You can measure decapsulation time to 1 cycle precision on a Cortex-M4. Sketch how KyberSlash1 recovers s.
16. An implementation compares only the first 1536 of 1568 ciphertext bytes. Build a plaintext-checking oracle from it.
17. You control a victim's ML-KEM private key file (expanded format). How do you make two different ciphertexts decapsulate to the same K, and why does a seed-only key stop you?
18. A middlebox drops ClientHellos larger than one packet. What does the client see, and how do Chrome and Go fall back?

### Connection
19. How is FO re-encryption related to the "decrypt then verify" idea in authenticated encryption, and how is it different?
20. How does ML-KEM's compression relate to Learning With Rounding (LWR) and Saber?
21. Why can't Signal's Double Ratchet simply swap X25519 for ML-KEM, and what does SPQR do instead?

### Open
22. Is the module structure exploitable? What would a Cramer–Ducas–Wesolowski-style result for modules need?
23. What is the "right" cost model for lattice sieving (gates vs memory access vs area-time), and how does the choice move ML-KEM-512 relative to category 1?
24. Can constant-time guarantees be established end to end, from spec to silicon?

### Answers

<details><summary>1. Which term cancels?</summary>

sᵀAᵀy. The sender's v contains tᵀy = (As+e)ᵀy = sᵀAᵀy + eᵀy. The receiver computes sᵀu′ = sᵀAᵀy + sᵀe₁ + sᵀc_u. Only the s-part of t needs cancelling, because the e-part eᵀy is already small. That is why the secret key is s alone.
</details>

<details><summary>2. Why sample Â in the NTT domain?</summary>

A uniform polynomial maps to a uniform NTT vector (the NTT is a bijection), so sampling Â directly is statistically identical and skips k² forward NTTs. If the standard defined A in the coefficient domain, every implementation would pay k² extra transforms, and test vectors would differ. FIPS 203 makes the NTT normative for exactly this reason.
</details>

<details><summary>3. Secret-dependent values in decaps</summary>

ŝ, the intermediate w = v′ − sᵀu′, the decoded m′, (K′, r′) = G(m′‖h), every value inside the re-encryption (y′, e₁′, e₂′, u, v before compression), the comparison result, and z. KyberSlash1 leaked through Compress_1(w) in poly_tomsg (division of a w-derived numerator by q). KyberSlash2 leaked through Compress_du/dv in poly_compress during re-encryption, where the inputs depend on m′ and r′.
</details>

<details><summary>4. Why use the stored H(ek)?</summary>

For speed: hashing 1184 bytes on every decapsulation costs time. FIPS 203 requires a "hash check" on dk import (H(ek part) == stored h). Without that check a malicious or corrupted dk can carry an h unrelated to ek. Then K and r are derived from the wrong h, re-encryption fails or binds to the wrong key, and that is one ingredient of the MAL-BIND attacks. Seed-only keys rebuild everything, so this can't happen.
</details>

<details><summary>5. Flip one bit of c₂</summary>

One 4-bit nibble of v changes, moving one coefficient by 208 (or more if a high bit flipped). Decrypt may or may not still produce m′ (noise ±76 + 208 is usually still below 832, so m′ often doesn't change). Re-encryption from m′ then gives the original c, which differs from the tampered c in that bit, so Decaps returns J(z‖c_tampered): a pseudorandom key unrelated to K. The sender's K and the receiver's K disagree, and the handshake fails at key confirmation. No error comes from the KEM itself.
</details>

<details><summary>6. Why 3329?</summary>

A fast NTT needs n | (q−1) with n = 256. The primes 257 and 769 qualify, but they leave too little room: q/4 would be about 64 or 192, smaller than the noise needed for security. Reaching δ ≈ 2^-128 or lower for CCA wouldn't work. 3329 is the next qualifying prime, fits 12 bits, and keeps products under 2^24. It only has 256th roots of unity (not 512th), hence the incomplete NTT.
</details>

<details><summary>7. Why dv = 4 dominates</summary>

The rounding error for d bits is roughly uniform with width q/2^d. For d = 4 that is 208, variance about 3608, against about 2213 for all sampled noise combined. Kyber accepts this because each extra bit of dv costs 32 bytes of ciphertext, and the bounded, uniform rounding noise hurts the failure tail much less than the same variance of unbounded noise would (see Q8). Rounding noise is effectively cheap.
</details>

<details><summary>8. Gaussian vs exact</summary>

The Gaussian treats the whole noise as unbounded with σ ≈ 76, putting failure at 10.9σ. In reality 62% of the variance (c_v) is bounded by ±104. Failure needs the remaining sum-of-products part (σ ≈ 47) to reach at least 728, which is 15.5σ, and that part is itself a sum of bounded products with sub-Gaussian tails. The exact convolution captures both effects.
</details>

<details><summary>9. Why implicit rejection?</summary>

An explicit ⊥ is a 1-bit oracle. Combined with even a weak side channel or a failure-boosting search, it speeds up key recovery and makes timing differences between paths easy to see. Returning J(z‖c) makes the reject path output look like a valid key, keeps the code path uniform (compute both, select in constant time), and gives tighter QROM proofs (FO with implicit rejection). The flag must never leave the function.
</details>

<details><summary>10. Why hybrid?</summary>

ML-KEM's hardness is a younger assumption than ECDH's. Chen's April 2024 scare showed how quickly confidence can wobble, and implementation bugs are still being found. A hybrid stays secure if *either* component holds, for about 32 extra bytes and microseconds. ANSSI and BSI require it. CNSA 2.0 accepts it.
</details>

<details><summary>11. No re-encryption</summary>

The attacker submits crafted (u, v) pairs, for example with v nudged near the decision boundary in one coefficient, and observes whether the derived key matches a guess (a plaintext-checking oracle via key confirmation). Each query reveals a linear inequality on s, and a few thousand queries recover s. This is exactly the key-mismatch attack on CPA Kyber.
</details>

<details><summary>12. Ephemeral-only</summary>

With truly one-time keys, chosen-ciphertext attacks get one query, so the FO transform and implicit rejection buy almost nothing, and a CPA KEM would do (as in TLS 1.3 ephemeral exchange). NIST kept full CCA because keys get reused in practice (caching, static server keys, HPKE, bugs), because one primitive for all uses is safer, and because re-encryption costs only one extra encryption.
</details>

<details><summary>13. Ring-LWE with n = 512</summary>

Gain: one big polynomial, slightly faster. Lose: each security level needs a different ring and NTT (n = 512 or 1024 and possibly a different q), and the scheme commits to a single ring structure (more algebraic structure per dimension). Module-LWE keeps one arithmetic core, and k scales security.
</details>

<details><summary>14. Drop H(ek) from G</summary>

Then r depends only on m, and the same (m → ciphertext) map holds for every public key's randomness derivation. An attacker can precompute "weak" m values whose noise terms are large and use the work against **all** keys at once (multi-target failure search). It also weakens binding of K to the recipient. H(ek) makes the work per key.
</details>

<details><summary>15. KyberSlash1 sketch</summary>

poly_tomsg divides (2w + 1665) by q, and the DIV timing jumps at numerator thresholds (for example 8192 on Zen 2). Craft ciphertexts with u = small multiples chosen so w's coefficients equal v − (coefficient of s) times a known value. Then whether a numerator crosses a threshold depends on one secret coefficient. Time thousands of decapsulations per ciphertext, classify slow vs fast, and solve for each coefficient of s in {−2..2}. Recovery took hours on a Raspberry Pi 2.
</details>

<details><summary>16. Partial comparison oracle</summary>

Modify only the last 32 bytes, which are part of c₂ (v's encoding). Re-encryption from m′ gives c′. If m′ didn't change, c′ equals the original c, and the truncated comparison over bytes 0..1535 matches, so Decaps returns the **real** K′ instead of K̄. If your modification flipped a message bit, K′ changes. So "does my modified ciphertext give the honest K?" reveals whether a coefficient crossed the boundary, which is a plaintext-checking oracle. Choose modifications to binary-search each coefficient of the noise and hence s. The wolfSSL PoC needed about 350 queries.
</details>

<details><summary>17. MAL-BIND attack</summary>

In the expanded dk you can set ŝ, ek, h and z independently. For example, choose ek and h inconsistent with ŝ so that re-encryption always fails. Then every ciphertext takes the reject path, K = J(z‖c), and you control z, so outputs are predictable to you. Or construct cases where two ciphertexts both reject to keys you can relate. Schmieg gives explicit constructions for K-CT and K-PK collisions. A 64-byte seed forces honest derivation of every component, so these inconsistencies can't be represented.
</details>

<details><summary>18. Oversized ClientHello</summary>

The connection stalls or resets after the first packet: the server read one segment, failed to parse it, and closed or waited. Chrome added enterprise policies and a flag, Go kept `GODEBUG=tlsmlkem=0`, and clients often send an X25519-only share as well. The real fix is servers that loop on read until the record is complete (tldr.fail).
</details>

<details><summary>19. FO vs AEAD</summary>

Both reject anything that wasn't produced honestly. AEAD does it with a MAC under a shared key. FO does it by recomputing the sender's deterministic encryption from the recovered m and checking for equality, which works without a shared secret because the randomness is a hash of the message. The difference: FO's check happens after decryption, so decryption itself must be side-channel safe, whereas AEAD verifies before decrypting.
</details>

<details><summary>20. Compression vs LWR</summary>

Learning With Rounding replaces sampled error with deterministic rounding (b = ⌊(p/q)·As⌉). ML-KEM's ciphertext compression is a partial LWR step on u and v, adding rounding noise on top of sampled noise. Kyber512's 118-bit core-SVP figure counts on that rounding ("akin to LWR"); without it the figure is 112. Saber went fully LWR with a power-of-two modulus.
</details>

<details><summary>21. Signal's ratchet</summary>

The DH ratchet works because each new public key, combined with the peer's last key, immediately gives a fresh shared secret (non-interactive). A KEM needs a round trip (ek one way, ct back) and about 2.3 KB. SPQR runs a separate ML-KEM Braid ratchet: send the 64-byte header early, stream erasure-coded chunks of ek and ct on ordinary messages, then mix the resulting key with the Double Ratchet output through a KDF.
</details>

<details><summary>22. Module structure</summary>

CDW exploits the unit group and class group of a cyclotomic field to shorten principal or ideal lattice vectors. Module lattices of rank at least 2 don't reduce to ideals directly. An attack would need a module analogue: an efficient way to reduce module lattice bases using the ring structure, beating plain BKZ at Kyber's approximation factors. Results so far (for example module-LLL) help only at large approximation factors. Open.
</details>

<details><summary>23. Cost model</summary>

Sieving in dimension β needs about 2^{0.2075β} memory and accesses it randomly. If memory access is free (the gate model), MATZOV-style estimates put Kyber-512 near 2^137.5, below 2^143. If you charge for distance (area-time or physically realistic RAM), costs rise by about 2^20 or more. NIST took the latter position, Bernstein disputed the arithmetic, and Ducas–Pulles disputed the attack's success probability. No consensus, so practice avoids 512.
</details>

<details><summary>24. End-to-end constant time</summary>

Partly. Spec→code correctness (hax/F*, EasyCrypt) and code→assembly constant-time (Jasmin, HOL Light) are done for some implementations. The remaining gap is assembly→silicon: variable-time multipliers, power and EM leakage, and speculative execution. That needs hardware leakage contracts (ISA-level guarantees like Intel DIT / Arm DIT) and masking. Open.
</details>

## 15. Go deeper next

1. **ML-DSA (FIPS 204) and Fiat–Shamir with aborts**: the same ring, but rejection sampling hides the secret in signatures. Why signatures are 2.4–4.6 KB, and what that means for TLS certificates.
2. **Masking lattice KEMs**: arithmetic↔Boolean conversions, why Compress and the FO comparison are the expensive parts, and the 2025 attacks on shuffled and masked code.
3. **Lattice sieving and BKZ**: how core-SVP numbers like 183 are computed, G6K/GPU sieving records (SVP-200), and the dual-attack dispute.

## Sources

**Standards and specs**
- FIPS 203: https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf
- Kyber round-3 spec v3.02: https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf
- NIST PQC timeline: https://csrc.nist.gov/projects/post-quantum-cryptography/workshops-and-timeline
- NIST IR 8413: https://nvlpubs.nist.gov/nistpubs/ir/2022/NIST.IR.8413-upd1.pdf
- NIST HQC selection: https://www.nist.gov/news-events/news/2025/03/nist-selects-hqc-fifth-algorithm-post-quantum-encryption
- SP 800-227: https://csrc.nist.gov/pubs/sp/800/227/final
- RFC 9935 (ML-KEM in X.509): https://www.rfc-editor.org/rfc/rfc9935.html
- draft-ietf-tls-ecdhe-mlkem: https://datatracker.ietf.org/doc/draft-ietf-tls-ecdhe-mlkem/
- draft-irtf-cfrg-hybrid-kems: https://datatracker.ietf.org/doc/draft-irtf-cfrg-hybrid-kems
- draft-sfluhrer-cfrg-ml-kem-security-considerations: https://datatracker.ietf.org/doc/html/draft-sfluhrer-cfrg-ml-kem-security-considerations-00
- TLS key-share prediction: https://www.ietf.org/archive/id/draft-ietf-tls-key-share-prediction-04.html

**Papers**
- Bos et al., CRYSTALS-Kyber (EuroS&P 2018): https://eprint.iacr.org/2017/634
- KyberSlash (TCHES 2025): https://eprint.iacr.org/2024/1049 · https://tches.iacr.org/index.php/TCHES/article/view/12046
- SPA on patched ML-KEM: https://eprint.iacr.org/2024/2051
- Formally Verifying Kyber Episode V (CRYPTO 2024): https://eprint.iacr.org/2024/843
- Formally verifying Kyber (TCHES 2023): https://tches.iacr.org/index.php/TCHES/article/view/10960
- Keeping Up with the KEMs (CCS 2024): https://eprint.iacr.org/2023/1933
- Unbindable Kemmy Schmidt: https://eprint.iacr.org/2024/523
- X-Wing: https://eprint.iacr.org/2024/039
- Triple Ratchet (Eurocrypt 2025): https://eprint.iacr.org/2025/078
- PQXDH analysis (USENIX Sec 2024): https://eprint.iacr.org/2024/702
- Guo–Johansson–Nilsson (CRYPTO 2020): https://eprint.iacr.org/2020/743
- Curse of Re-encryption (TCHES 2022): https://eprint.iacr.org/2021/849
- Pessl–Prokop fault attacks (TCHES 2021): https://eprint.iacr.org/2021/064
- (One) failure is not an option: https://eprint.iacr.org/2019/1399
- Fluhrer 2016: https://eprint.iacr.org/2016/085
- Key mismatch with limited reuse: https://eprint.iacr.org/2024/810 · https://cic.iacr.org/p/1/3/21
- Ducas–Pulles dual sieve (CRYPTO 2023): https://eprint.iacr.org/2023/302
- Ducas–Pulles score prediction: https://eprint.iacr.org/2023/1850
- Pouly–Shen provable dual attacks: https://eprint.iacr.org/2023/1508
- Provable FFT dual attack on ML-KEM (2026): https://eprint.iacr.org/2026/2166
- Chen quantum LWE (withdrawn): https://eprint.iacr.org/2024/555
- Barbosa–Hülsing QROM FO: https://eprint.iacr.org/2023/755
- Cramer–Ducas–Wesolowski: https://eprint.iacr.org/2016/885
- SWOOSH: https://eprint.iacr.org/2023/271
- Seiler AVX2 NTT: https://eprint.iacr.org/2018/039
- Shuffled Kyber CCA side channel: https://eprint.iacr.org/2025/1956
- Pointwise-mult template attack: https://eprint.iacr.org/2025/1577
- EM dataset: https://eprint.iacr.org/2026/1851
- Mind the Gap (IMC 2026): https://arxiv.org/abs/2607.29005
- ML-KEM AVX-512 cycles: https://arxiv.org/pdf/2404.13544
- Regev 2005: https://cims.nyu.edu/~regev/papers/qcrypto.pdf

**Code and docs**
- pq-crystals/kyber ref: https://github.com/pq-crystals/kyber
- mlkem-native: https://github.com/pq-code-package/mlkem-native
- libcrux: https://github.com/cryspen/libcrux
- Go crypto/mlkem: https://pkg.go.dev/crypto/mlkem
- OpenSSL EVP_PKEY-ML-KEM: https://docs.openssl.org/3.5/man7/EVP_PKEY-ML-KEM/
- BoringSSL mlkem.h: https://boringssl.googlesource.com/boringssl/+/HEAD/include/openssl/mlkem.h
- liboqs-python: https://github.com/open-quantum-safe/liboqs-python
- Clangover: https://github.com/antoonpurnal/clangover
- KyberSlash site: https://kyberslash.cr.yp.to/faq.html · https://kyberslash.cr.yp.to/libraries.html
- JEP 496: https://openjdk.org/jeps/496
- Go 1.24 notes: https://go.dev/doc/go1.24
- OpenSSL 3.5 notes: https://openssl-library.org/news/openssl-3.5-notes
- OpenSSH 10.0: https://www.openssh.com/txt/release-10.0

**Articles and engineering blogs**
- Cloudflare pq-2024: https://blog.cloudflare.com/pq-2024/ · pq-2025: https://blog.cloudflare.com/pq-2025/ · roadmap: https://blog.cloudflare.com/post-quantum-roadmap/ · radar: https://blog.cloudflare.com/radar-origin-pq-key-transparency-aspa/
- Google, new path for Kyber: https://security.googleblog.com/2024/09/a-new-path-for-kyber-on-web.html
- Signal SPQR: https://signal.org/blog/spqr/ · PQXDH: https://signal.org/blog/pqxdh/
- Apple iMessage PQ3: https://security.apple.com/blog/imessage-pq3/
- AWS PQ TLS: https://aws.amazon.com/blogs/security/ml-kem-post-quantum-tls-now-supported-in-aws-kms-acm-and-secrets-manager/
- Amazon Science, verifying PQC: https://www.amazon.science/blog/verifying-and-optimizing-post-quantum-cryptography-at-amazon
- Cryspen ML-KEM verification: https://cryspen.com/post/ml-kem-verification/
- Filippo Valsorda, mlkem768: https://words.filippo.io/mlkem768/
- Bernstein, "The inability to count correctly": https://blog.cr.yp.to/20231003-countcorrectly.html
- MATZOV report: https://zenodo.org/records/6412487
- Symbolic Software Crucible: https://symbolic.software/blog/2026-03-23-crucible
- tldr.fail: https://tldr.fail/
- Scott Aaronson on Chen: https://scottaaronson.blog/?p=7946
- Mullvad: https://mullvad.net/blog/quantum-resistant-tunnels-are-now-the-default-on-desktop
- wolfSSL CVE-2026-10097 (aggregator): https://app.opencve.io/cve/CVE-2026-10097
