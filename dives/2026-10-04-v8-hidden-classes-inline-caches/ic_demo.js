// Run: node --allow-natives-syntax ic_demo.js
// Optional: node --allow-natives-syntax --trace-deopt --trace-opt ic_demo.js | grep -i "getX"

// ---- Part 1: shapes. Same props, same order => same Map. Different order => different Map.
const a = { x: 1, y: 2 };
const b = { x: 3, y: 4 };
const c = { y: 2, x: 1 };
console.log("a,b share Map?", %HaveSameMap(a, b));   // true
console.log("a,c share Map?", %HaveSameMap(a, c));   // false (transition tree took a different path)

// ---- Part 2: delete => dictionary mode (slow properties)
const d = { x: 1, y: 2, z: 3 };
console.log("fast before delete:", %HasFastProperties(d)); // true
delete d.x;
console.log("fast after delete :", %HasFastProperties(d)); // false (dictionary mode)
const e = { x: 1, y: 2, z: 3 };
e.x = undefined; // alternative to delete
console.log("fast after x=undefined:", %HasFastProperties(e)); // true

// ---- Part 3: elements kinds. Inspect with %DebugPrint(arr) -> look for "elements kind".
const arr = [1, 2, 3];          // PACKED_SMI_ELEMENTS
arr.push(1.5);                  // -> PACKED_DOUBLE_ELEMENTS
arr.push("s");                  // -> PACKED_ELEMENTS
// %DebugPrint(arr);            // uncomment to see the kind (noisy)

// ---- Part 4: IC state vs speed. One call site, 1 / 4 / 8 distinct shapes.
function getX(o) { return o.x; }

function makeShapes(n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const o = {};
    o["p" + i] = i;   // distinct leading property => distinct Map
    o.x = i;
    out.push(o);
  }
  return out;
}

function bench(label, shapes) {
  const N = 20_000_000;
  const len = shapes.length;
  // warm up so getX is optimized with this feedback
  let s = 0;
  for (let i = 0; i < 2_000_000; i++) s += getX(shapes[i % len]);
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < N; i++) s += getX(shapes[i % len]);
  const t1 = process.hrtime.bigint();
  console.log(label.padEnd(26), (Number(t1 - t0) / N).toFixed(2), "ns/call", "(sink", s % 7, ")");
}

// NOTE: getX feedback is cumulative: it only ever moves mono -> poly -> mega.
// So run in this order, and use fresh copies of the function (eval) if you want clean per-state numbers.
function fresh() { return new Function("o", "return o.x"); }
function benchFresh(label, n) {
  const f = fresh();
  const shapes = makeShapes(n);
  const N = 20_000_000, len = shapes.length;
  let s = 0;
  for (let i = 0; i < 2_000_000; i++) s += f(shapes[i % len]);
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < N; i++) s += f(shapes[i % len]);
  const t1 = process.hrtime.bigint();
  console.log(label.padEnd(26), (Number(t1 - t0) / N).toFixed(2), "ns/call", "(sink", s % 7, ")");
}

benchFresh("monomorphic (1 shape)", 1);
benchFresh("polymorphic (4 shapes)", 4);
benchFresh("megamorphic (8 shapes)", 8);
benchFresh("megamorphic (64 shapes)", 64);
