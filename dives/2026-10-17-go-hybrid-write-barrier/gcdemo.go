// gcdemo: park many goroutines, churn pointers on the heap, and read GC pause stats.
// Run:  go run gcdemo.go -g 100000
//       GODEBUG=gctrace=1 go run gcdemo.go -g 100000 2>&1 | tail -20
package main

import (
	"flag"
	"fmt"
	"runtime"
	"sort"
	"time"
)

type node struct {
	next *node
	pad  [6]uint64
}

var sink *node

func park(depth int, ch chan struct{}) {
	var pad [32]uintptr // give each stack a little weight
	_ = pad
	if depth > 0 {
		park(depth-1, ch)
		return
	}
	<-ch
}

func main() {
	g := flag.Int("g", 100000, "idle goroutines")
	secs := flag.Int("s", 3, "seconds of pointer churn")
	flag.Parse()

	ch := make(chan struct{})
	for i := 0; i < *g; i++ {
		go park(8, ch)
	}
	time.Sleep(200 * time.Millisecond)

	// pointer churn: every store below goes through the write barrier while a mark phase is on
	var ring [4096]*node
	end := time.Now().Add(time.Duration(*secs) * time.Second)
	for time.Now().Before(end) {
		for i := range ring {
			n := &node{}
			n.next = ring[(i*7)%len(ring)]
			ring[i] = n
		}
		sink = ring[0]
	}

	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	var p []uint64
	for i := 0; i < int(ms.NumGC) && i < 256; i++ {
		p = append(p, ms.PauseNs[i])
	}
	sort.Slice(p, func(i, j int) bool { return p[i] < p[j] })
	var max uint64
	if len(p) > 0 {
		max = p[len(p)-1]
	}
	fmt.Printf("goroutines=%d GCs=%d max STW pause=%.0fus total STW=%.1fms GC CPU fraction=%.3f\n",
		*g, ms.NumGC, float64(max)/1e3, float64(ms.PauseTotalNs)/1e6, ms.GCCPUFraction)
	close(ch)
}
