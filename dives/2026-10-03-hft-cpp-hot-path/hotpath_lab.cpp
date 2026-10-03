// hotpath_lab.cpp — three ~30-second experiments behind HFT C++ folklore.
//
//   1. false sharing   : two threads bump counters on the same vs separate cache lines
//   2. cold vs warm    : the same "on_tick" work, measured after the cache was trashed
//                        (what an idle trading thread sees) vs right after a warm-up
//   3. order book scan : std::map vs a reversed sorted std::vector with linear search
//                        (best price lives at the back, most updates land near it)
//
// Build:  c++ -O2 -std=c++20 -pthread hotpath_lab.cpp -o lab && ./lab
// Portable (x86-64 and arm64). Timings use steady_clock, so single-event numbers are
// coarse (~tens of ns resolution on some platforms); we report percentiles over many runs.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <map>
#include <random>
#include <thread>
#include <vector>

using clk = std::chrono::steady_clock;
static inline uint64_t now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(clk::now().time_since_epoch()).count();
}

template <class T> static void do_not_optimize(T const& v) { asm volatile("" : : "r,m"(v) : "memory"); }

static void print_pcts(const char* label, std::vector<uint64_t>& v) {
    std::sort(v.begin(), v.end());
    auto p = [&](double q) { return v[std::min(v.size() - 1, size_t(q * v.size()))]; };
    std::printf("  %-28s p50=%6llu ns  p99=%6llu ns  p99.9=%6llu ns  max=%7llu ns\n", label,
                (unsigned long long)p(.50), (unsigned long long)p(.99), (unsigned long long)p(.999),
                (unsigned long long)v.back());
}

// ---------------------------------------------------------------- 1. false sharing
// 128 covers both x86 (64B line, adjacent-line prefetcher pulls pairs) and Apple M (128B).
constexpr size_t kLine = 128;

struct Shared { std::atomic<uint64_t> a{0}, b{0}; };                 // same line
struct Padded { alignas(kLine) std::atomic<uint64_t> a{0};
                alignas(kLine) std::atomic<uint64_t> b{0}; };        // separate lines

template <class S> static double run_counters(uint64_t iters) {
    S s;
    auto t0 = clk::now();
    std::thread t1([&] { for (uint64_t i = 0; i < iters; ++i) s.a.fetch_add(1, std::memory_order_relaxed); });
    std::thread t2([&] { for (uint64_t i = 0; i < iters; ++i) s.b.fetch_add(1, std::memory_order_relaxed); });
    t1.join(); t2.join();
    return std::chrono::duration<double, std::milli>(clk::now() - t0).count();
}

// ---------------------------------------------------------------- 2. cold vs warm
// "Hot path": touch a 32 KiB working set (book levels + strategy params) and do a little math.
static std::vector<uint64_t> g_state(4096, 1);   // 32 KiB
static std::vector<uint8_t>  g_junk(64 << 20);   // 64 MiB to evict caches

__attribute__((noinline)) static uint64_t on_tick(uint64_t px) {
    uint64_t acc = px;
    for (size_t i = 0; i < g_state.size(); i += 8) acc += g_state[i] * (px ^ i);   // 512 lines
    return acc;
}
static void trash_caches() {
    for (size_t i = 0; i < g_junk.size(); i += 64) g_junk[i]++;
}

// ---------------------------------------------------------------- 3. order book
// Bid side. Prices in integer ticks. Best bid = highest price.
struct VecBook {
    // sorted ascending -> best bid at back(); inserts near the top are cheap (few elements moved)
    std::vector<std::pair<int64_t, int64_t>> lv;   // (price, qty)
    void update(int64_t px, int64_t qty) {
        auto it = lv.end();
        while (it != lv.begin() && (it - 1)->first > px) --it;        // linear scan from the back
        if (it != lv.begin() && (it - 1)->first == px) {
            if (qty == 0) lv.erase(it - 1); else (it - 1)->second = qty;
        } else if (qty) lv.insert(it, {px, qty});
    }
    int64_t best() const { return lv.empty() ? 0 : lv.back().first; }
};
struct MapBook {
    std::map<int64_t, int64_t, std::greater<>> lv;  // node-based, one allocation per new level
    void update(int64_t px, int64_t qty) { if (qty == 0) lv.erase(px); else lv[px] = qty; }
    int64_t best() const { return lv.empty() ? 0 : lv.begin()->first; }
};

template <class B> static void bench_book(const char* name, const std::vector<std::pair<int64_t,int64_t>>& ops) {
    // Per-op timing is below clock resolution, so time the whole batch; best of 5 runs.
    double best = 1e18;
    for (int rep = 0; rep < 5; ++rep) {
        B b;
        for (int i = 0; i < 200; ++i) b.update(10000 - i, 100);        // 200 resting levels
        uint64_t t = now_ns();
        int64_t sink = 0;
        for (auto [px, q] : ops) { b.update(px, q); sink += b.best(); }
        do_not_optimize(sink);
        best = std::min(best, double(now_ns() - t) / ops.size());
    }
    std::printf("  %-28s %.1f ns/update\n", name, best);
}

int main() {
    std::printf("1) false sharing — 2 threads x 50M relaxed fetch_add\n");
    std::printf("  same line : %.0f ms\n", run_counters<Shared>(50'000'000));
    std::printf("  padded    : %.0f ms\n\n", run_counters<Padded>(50'000'000));

    std::printf("2) cold vs warm hot path (2000 samples each)\n");
    std::vector<uint64_t> cold, warm;
    for (int i = 0; i < 2000; ++i) {
        trash_caches();                                  // idle thread: someone else used the cache
        uint64_t t = now_ns(); do_not_optimize(on_tick(i)); cold.push_back(now_ns() - t);
        on_tick(i + 1);                                  // "warm-up" call (the dummy order)
        t = now_ns(); do_not_optimize(on_tick(i + 2)); warm.push_back(now_ns() - t);
    }
    print_pcts("cold (after cache trash)", cold);
    print_pcts("warm (after warm-up call)", warm);
    std::printf("\n");

    std::printf("3) order book update, 1M ops, 90%% within 5 ticks of best\n");
    std::mt19937_64 rng(42);
    std::vector<std::pair<int64_t, int64_t>> ops;
    for (int i = 0; i < 1'000'000; ++i) {
        bool near = rng() % 10 != 0;
        int64_t px = 10000 - int64_t(near ? rng() % 5 : rng() % 200);
        int64_t q = (rng() % 4 == 0) ? 0 : int64_t(rng() % 500 + 1);
        ops.push_back({px, q});
    }
    bench_book<MapBook>("std::map<greater>", ops);
    bench_book<VecBook>("reversed vector + linear", ops);
    std::printf("\n(clock overhead itself is ~20-40 ns on most machines; compare relative numbers)\n");
}
