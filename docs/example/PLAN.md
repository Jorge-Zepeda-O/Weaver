# weaver — the plan that built it

**Goal:** python -m weaver build turns this file into a clickable HTML graph, a Markdown table and a PDF, with every view tested.

One plan file, three views. A0 is the shared contract and lands first; the A2→A3 strand runs in parallel with the main strand; M1 is the only merge, and the end-to-end test guards it. V1 is the release the merge became.

| ID | Kind | Title | Group | Status | Dimensions | Verify | Depends on |
|---|---|---|---|---|---|---|---|
| A0 | atom | Data contract: Plan model + TOML schema | main | ✓ done | ↕P ↔F ⤓M | tests/test_load.py | — |
| A1 | atom | Loader + validator | main | ✓ done | ↕L ↔N ⤓M | tests/test_load.py | A0 |
| A2 | atom | Graphviz export: .dot + SVG | graph | ✓ done | ↕L ↔F ⤓M | tests/test_dot.py | A0 |
| A3 | atom | HTML view: zoom, pan, pinch, click → modal | graph | ✓ done | ↕L ↔F ⤓H | tests/test_html.py, tests/test_gestures.py | A0, A2 |
| A4 | atom | Markdown table export | main | ✓ done | ↕I ↔1 ⤓E | tests/test_views_md_pdf.py | A1 |
| A5 | atom | PDF view: graph + caption + field notes | main | ✓ done | ↕I ↔1 ⤓E | tests/test_views_md_pdf.py | A0, A2 (runtime) |
| M1 | merge | CLI build + end-to-end test | main | ✓ done | ↕P ↔F ⤓E | tests/test_cli.py | A1, A3, A4, A5 |
| V1 | release | v0.1.0: tagged and published | main | ✓ done | ↕P ↔1 ⤓E | the v0.1.0 tag and its release page | M1 |
| A6 | atom | Overlaps in every view | graph | ○ todo | ↕L ↔F ⤓M | tests/test_overlap_views.py | A3 |

**Key:**

- ↕ scope: I independent, L local, P project, U umbrella, G global, ? unknowable
- ↔ amount: 1 one, F few, N numerous, B bulk, S stream, ? unknowable
- ⤓ complexity: T trivial, E easy, M moderate, H hard, N novel, ? unknowable
- - unassessed; ? assessed but unknowable, ranks worst

**Overlaps:**

- weaver/markdown.py — A4 (main) × A6 (graph) — A4 landed in M1: if A6 builds on M1, add it to A6's deps — acknowledged: A6 only appends a list after the key that A4 writes

## Field notes

### A0: Data contract: Plan model + TOML schema

- **Status**: ✓ done
- **Group**: main
- **Dimensions**: ↕P ↔F ⤓M
- **Verify**: tests/test_load.py

The contract every other atom builds against: Plan, Node, Dep, Edge in weaver/model.py, plus this file as the schema example.
Lands first, so the parallel strands share no other file.

### A1: Loader + validator

- **Status**: ✓ done
- **Group**: main
- **Dimensions**: ↕L ↔N ⤓M
- **Verify**: tests/test_load.py

load_plan / parse_plan. Reports every error in one run: unknown keys, bad ids, kinds, statuses and codes, unknown or duplicate deps, self-deps, cycles (with the path), a missing or unknown schema version.

### A2: Graphviz export: .dot + SVG

- **Status**: ✓ done
- **Group**: graph
- **Dimensions**: ↕L ↔F ⤓M
- **Verify**: tests/test_dot.py

Shape by kind (atom vs merge), line style by seam (build solid, runtime dashed), fill by status, lanes by group, border colour by scope and border weight by complexity.
Contract with A3 and A5: every SVG node group carries id="node-<id>".

### A3: HTML view: zoom, pan, pinch, click → modal

- **Status**: ✓ done
- **Group**: graph
- **Dimensions**: ↕L ↔F ⤓H
- **Verify**: tests/test_html.py, tests/test_gestures.py

One self-contained file, no CDN. Node data travels as escaped JSON; the modal fills via textContent only, never innerHTML. A Content-Security-Policy admits the one script and the one style block by hash.
Gesture handling is a DOM-free core, tested under Node.

### A4: Markdown table export

- **Status**: ✓ done
- **Group**: main
- **Dimensions**: ↕I ↔1 ⤓E
- **Verify**: tests/test_views_md_pdf.py

The view GitHub can render. Pipes and newlines in cells are escaped.

### A5: PDF view: graph + caption + field notes

- **Status**: ✓ done
- **Group**: main
- **Dimensions**: ↕I ↔1 ⤓E
- **Verify**: tests/test_views_md_pdf.py

WeasyPrint, no JavaScript: the static stand-in for the modals.
Runtime seam on A2 because it consumes the SVG A2 produces, not A2's code.

### M1: CLI build + end-to-end test

- **Status**: ✓ done
- **Group**: main
- **Dimensions**: ↕P ↔F ⤓E
- **Verify**: tests/test_cli.py

python -m weaver build PLAN.toml -o out/ → PLAN.html, PLAN.md, PLAN.pdf, plan.svg.
The end-to-end test is the oracle for the merge.

### V1: v0.1.0: tagged and published

- **Status**: ✓ done
- **Group**: main
- **Dimensions**: ↕P ↔1 ⤓E
- **Verify**: the v0.1.0 tag and its release page

A release is a merge that marks where a version was cut (schema 2), drawn as an octagon with bold purple text.
Shortened for the example: a port into the repository and a schema pass sat between M1 and the tag.

### A6: Overlaps in every view

- **Status**: ○ todo
- **Group**: graph
- **Dimensions**: ↕L ↔F ⤓M
- **Verify**: tests/test_overlap_views.py

Still open, so the example shows an overlap: A6 and A4 both touch weaver/markdown.py from different lanes, and nothing orders them.
The [[overlap]] entry below says why that is fine; without it, check --strict would fail.
