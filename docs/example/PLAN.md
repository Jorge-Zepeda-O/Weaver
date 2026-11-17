# weaver — the plan that built it

**Goal:** python -m weaver build turns this file into a clickable HTML graph, a Markdown table and a PDF, with every view tested.

One plan file, three views. A0 is the shared contract and lands first; the A2→A3 strand runs in parallel with the main strand; M1 is the only merge, and the end-to-end test guards it.

| ID | Kind | Title | Group | Status | Dimensions | Verify | Depends on |
|---|---|---|---|---|---|---|---|
| A0 | atom | Data contract: Plan model + TOML schema | main | ✓ done | S:P A:F C:M | tests/test_load.py | — |
| A1 | atom | Loader + validator | main | ✓ done | S:L A:N C:M | tests/test_load.py | A0 |
| A2 | atom | Graphviz export: .dot + SVG | graph | ✓ done | S:L A:F C:M | tests/test_dot.py | A0 |
| A3 | atom | HTML view: zoom, pan, pinch, click → modal | graph | ✓ done | S:L A:F C:H | tests/test_html.py, tests/test_gestures.py | A0, A2 |
| A4 | atom | Markdown table export | main | ✓ done | S:I A:1 C:E | tests/test_views_md_pdf.py | A1 |
| A5 | atom | PDF view: graph + caption + field notes | main | ✓ done | S:I A:1 C:E | tests/test_views_md_pdf.py | A0, A2 (runtime) |
| M1 | merge | CLI build + end-to-end test | main | ✓ done | S:P A:F C:E | tests/test_cli.py | A1, A3, A4, A5 |

**Key:**

- S = scope: I independent, L local, P project, U umbrella, G global, ? unknowable
- A = amount: 1 one, F few, N numerous, B bulk, S stream, ? unknowable
- C = complexity: T trivial, E easy, M moderate, H hard, N novel, ? unknowable
- - unassessed; ? assessed but unknowable, ranks worst

## Field notes

### A0: Data contract: Plan model + TOML schema

The contract every other atom builds against: Plan, Node, Dep, Edge in weaver/model.py, plus this file as the schema example.
Lands first, so the parallel strands share no other file.

### A1: Loader + validator

load_plan / parse_plan. Reports every error in one run: unknown keys, bad ids, kinds, statuses and codes, unknown or duplicate deps, self-deps, cycles (with the path), a missing or unknown schema version.

### A2: Graphviz export: .dot + SVG

Shape by kind (atom vs merge), line style by seam (build solid, runtime dashed), fill by status, lanes by group, border colour by scope and border weight by complexity.
Contract with A3 and A5: every SVG node group carries id="node-<id>".

### A3: HTML view: zoom, pan, pinch, click → modal

One self-contained file, no CDN. Node data travels as escaped JSON; the modal fills via textContent only, never innerHTML. A Content-Security-Policy admits the one script and the one style block by hash.
Gesture handling is a DOM-free core, tested under Node.

### A4: Markdown table export

The view GitHub can render. Pipes and newlines in cells are escaped.

### A5: PDF view: graph + caption + field notes

WeasyPrint, no JavaScript: the static stand-in for the modals.
Runtime seam on A2 because it consumes the SVG A2 produces, not A2's code.

### M1: CLI build + end-to-end test

python -m weaver build PLAN.toml -o out/ → PLAN.html, PLAN.md, PLAN.pdf, plan.svg.
The end-to-end test is the oracle for the merge.
