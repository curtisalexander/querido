# Extensibility mechanism for qdo: research notes and quasi-plan

> **Status:** research / parking lot. Not committed work. Captured 2026-05-02
> while exploring what an extension surface for qdo would look like, inspired
> by the Pi coding agent's self-modifying / "minimal agent within" pattern.
>
> **Audience:** future-me and any contributor weighing whether qdo should
> evolve from "an opinionated set of commands" toward "an opinionated *core*
> with a sanctioned mutation surface." Read [DIFFERENTIATION.md](../../DIFFERENTIATION.md)
> first; this doc tests its invariants against an idea that *almost* violates
> them.

---

## Why this doc exists

qdo today is a fixed surface: ~32 commands across 10 categories, all shipped in
the wheel. Two extension-shaped surfaces already exist — **workflows** (YAML
that orchestrates existing commands) and **metadata** (user-authored YAML
captured into the compounding loop) — but neither lets a user *add new
primitives*. New connectors, new quality checks, new output formats, new
metadata fields, site-specific commands at work where code can't leave the
network: all currently require a fork or a PR.

Two real audiences want more:

1. **The user with a one-off need.** "I just want to do a small data thing
   that qdo doesn't do, and I want to ship it in an afternoon."
2. **The user with a workplace context.** "I have private knowledge that
   shouldn't go in your repo, but I want qdo to encode it."

And one architectural pull: **agents using qdo can already build extensions
faster than I can ship features.** If the surface is right, the agent is the
distribution mechanism.

The risk is symmetric: an extension surface fragments the compounding-loop
story that DIFFERENTIATION.md treats as the moat. The point of this doc is to
name both forces precisely enough that we can decide whether to build it.

---

## The Pi-shaped insight

Pi (`@mariozechner/pi-coding-agent`) is a coding agent built on a deliberately
small core — Read, Write, Edit, Bash plus an extension system. Two ideas matter
for qdo:

1. **"Don't download an extension. Ask the agent to extend itself."**
   ([Ronacher, 2026‑01‑31](https://lucumr.pocoo.org/2026/1/31/pi/)) Pi ships
   self-documentation that an agent reads, then has the agent write a new
   TypeScript module under `~/.pi/agent/extensions/` (global) or
   `.pi/extensions/` (project) and `/reload` to pick it up. The agent owns the
   extension because the agent wrote the extension.

2. **"Software malleable like clay — but the malleability has to be designed
   in."** Hot-reload, in-tree event hooks (`pi.registerTool`,
   `pi.registerCommand`, `pi.on(...)`), and an `ExtensionAPI` surface aren't
   afterthoughts. They sit at the centre, and the small core orbits them.

Pi extension capabilities, paraphrased from
[`pi-mono/.../extensions.md`](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md):
register tools the LLM can call, register slash commands, intercept tool
events to add permission gates, persist state across sessions, render custom
TUI dialogs. Distribution and isolation are deliberately under-specified — Pi
runs extensions in-process with full host access and treats trust as a
human-in-the-loop concern.

The cleanest sentence to carry into qdo: **the agent is already the
distribution mechanism. Stop pretending the project is a closed set of
commands.**

---

## The tension with qdo's mission

Pi is a *generic* agent harness — it has no opinion to dilute. qdo is the
opposite: its differentiator is the **opinionated** loop
`catalog → context → metadata → query → report/bundle`. Three invariants from
DIFFERENTIATION.md sit awkwardly against a plugin model:

- *"Prefer one mechanism over two."* We already have workflows. Adding
  extensions risks two parallel extension surfaces.
- *"Files, not services. Files, not marketplaces."* Extensions are file-shaped,
  good — but a marketplace would violate this and is the natural next pull.
- *"Deterministic tools. No LLM in qdo."* Extensions could trivially smuggle
  LLM calls into the tool layer.

And the loop itself: if any user can register `qdo my-thing`, the canonical
story fragments. Future agents reading SKILL.md plus a project's local
extensions get a confused picture of "what qdo is."

**The reconciling frame, if there is one:** extensions add *new primitives*
to the bottom of the stack; they do not edit the *promoted* loop at the top.
Workflows orchestrate. Metadata persists. Extensions extend. The compounding
loop stays first-class; extensions feed *into* it (a custom quality check
writes to the same `next_steps` graph; a custom connector serves the same
`context` command) rather than around it. If we can hold that line, the moat
survives. If we can't, this proposal makes qdo into Datasette + plugins, which
DIFFERENTIATION.md explicitly rejects.

---

## What "extensible qdo" could look like

A sketch, intentionally unimplemented. The shape below is what would survive
the invariants if we kept discipline.

### Extension types (categorized by hook point)

| Type | Hooks into | Concrete example |
|------|-----------|------------------|
| **Command** | New `qdo <name>` subcommand | `qdo geo-summary` for spatial columns |
| **Connector** | New `type` in connections.toml + Connector Protocol impl | Postgres, Trino, BigQuery |
| **Quality check** | Called from `qdo quality` | Phone-format regex, FK-existence check |
| **Metadata field** | New YAML key with validator + auto-fill rule | `pii_class`, `business_owner` |
| **Output format** | New `-f <name>` renderer | Mermaid ERD, org-mode |
| **Next-steps rule** | Augments suggestion graph | "after `geo-summary`, suggest `dist`" |
| **Workflow step type** | Callable referenced from workflow YAML | Internal lineage API call |

This is not a marketplace — it's a typed set of seven hook surfaces, each one
well-defined, each one mappable to an existing invariant. The list is the
contract: if a use case doesn't fit one of these, it isn't an extension, it's
a fork.

### Discovery and loading

- **Local files first.** Project: `.qdo/extensions/*.py`. User:
  `~/.config/qdo/extensions/*.py` (and platform-equivalents via `platformdirs`).
  No package install required — drop a `.py` in the directory, it works.
- **Entry-points second.** `[project.entry-points."querido.extensions"]` for
  pip-installable plugins. Same SDK, same hooks. This is the path for "share
  with team via a private package index."
- **Lazy by construction.** Startup only enumerates *paths*. The first time
  `qdo <subcommand>` is run, only the file(s) registering that subcommand
  import — preserving the "pay for what you use" invariant. Connector and
  output-format extensions follow the same pattern (load on first use).
- **Single-process, single-shot.** qdo is invoked-and-exits each call, which
  sidesteps Pi's hot-reload problem entirely. Every call is a fresh process;
  every edit to a `.py` is "live" on the next invocation. No `/reload`
  primitive needed.

### The SDK shape

A single import surface, e.g. `from querido.ext import qdo`. Decorators bind
to hook points, type hints are required (we already have `ty` in CI):

```python
# .qdo/extensions/phone_format.py
from querido.ext import qdo

@qdo.quality_check(name="phone_format", applies_to="varchar")
def check_phone_format(values: list[str]) -> list[str]:
    """Return values that don't match E.164."""
    import re
    pat = re.compile(r"^\+\d{10,15}$")
    return [v for v in values if v and not pat.match(v)]
```

```python
# .qdo/extensions/postgres_connector.py
from querido.ext import qdo
from querido.connectors.base import Connector

@qdo.connector(type_name="postgres")
class PostgresConnector(Connector):
    dialect = "postgres"
    # ... protocol implementation
```

The SDK does the envelope wiring for command extensions: a decorated function
returns a dict of `data`, the SDK wraps it in `{command, data, next_steps,
meta}` so the envelope contract holds for free.

### The agent self-extension path (the Pi-bit)

The piece worth borrowing wholesale:

- `qdo extension scaffold <name> --type <kind>` writes a starter file with
  imports, the right decorator, type-checked stubs, and a passing test fixture
  alongside.
- `qdo extension docs` prints the extension SDK reference — the same doc the
  agent reads to author one. (Bundle this into `qdo agent install` so any
  agent harness gets it for free.)
- `qdo extension example <kind>` emits a known-good reference extension to
  copy from — a hand-tuned `quality_check_phone_format.py`, a minimal
  `connector_csv_directory.py`, etc.
- `qdo extension list / show / test / disable` — diagnose, validate, and
  toggle without editing files by hand.
- SKILL.md gains a short *"if qdo doesn't have X"* section: scaffold → edit
  → `qdo extension test` → use. The agent's loop closes locally. No PR
  required for personal or work-internal needs.

This is the Pi pattern translated into Python's shipping conventions. The
agent is the author; qdo is the typed, documented host.

---

## What we deliberately wouldn't borrow from Pi

| Pi feature | Why qdo skips it |
|-----------|------------------|
| Marketplace / community registry | Files-as-primitives. Sharing is "send the `.py`" or "pip install". |
| In-tree LLM calls from extensions | Violates "no LLM in qdo". Extensions can call external APIs but the SDK doesn't paper over it. |
| Custom TUI overlays from extensions | Out of scope for v1. `qdo explore` stays first-class; extensions are CLI-shaped. |
| Hot-reload primitive | Unneeded. Each `qdo` invocation is a fresh process. |
| Same-process unrestricted execution | Borrowed, but with louder framing: extensions run as user code, with a first-load trust prompt and a `qdo extension trust` command to bless a fingerprint. Same risk model as `~/.bashrc`; we say so out loud. |
| Sandbox isolation | Out of scope. Pi doesn't have it either; honest documentation beats a leaky illusion. |

---

## The "rewrite built-ins as extensions" question

The user raised this directly: *"We could even think of some of the current
features as just extensions / plugins where we ship an initial opinionated
set."* This is the Pi-style minimal-core framing.

**Recommendation: don't, at least not for v1.** Reasons:

1. The opinionated loop *is* the differentiator. Demoting `catalog`,
   `context`, `metadata`, `quality`, `report`, `bundle` to "just extensions
   we happen to ship" reframes qdo as "a plugin runtime with some defaults" —
   which is exactly the Datasette positioning IDEAS.md rejects.
2. Extensions add a serialization tax (decorators, registration, lazy import
   plumbing). Paying that tax for shipped commands earns no user-visible
   benefit; the cost lands on the maintainer for years.
3. The eval suite (`scripts/eval_skill_files_claude.py`) is calibrated against
   the shipped command set. Re-routing those commands through a registration
   layer is a regression risk for zero gain.

The honest framing is: **qdo has an opinionated first-class loop. Extensions
extend that loop, they don't replace it.** That sentence is the boundary
condition.

---

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Extension fragments the canonical SKILL.md story | Extension-defined commands don't appear in promoted workflow; `qdo --help` separates "Built-in" from "Extension" sections. |
| Extension shadows a built-in command/format/check | Name collisions are a startup error, not silent override. Built-ins win. |
| Eval suite becomes flaky on user systems | Eval runs with `QDO_EXT_DISABLED=1`. Extensions don't load during evals. |
| LLM calls leak into the tool layer | SDK reference explicitly forbids it; lint/audit checks `from anthropic` / `from openai` / `requests.post(...api...)` patterns in extension code on `qdo extension test`. Soft enforcement; the goal is friction, not impossibility. |
| Two-mechanism drift with workflows | Boundary doc: workflows orchestrate `qdo` invocations, extensions add new `qdo` invocations. They compose: a workflow can call an extension-defined command, but never embed Python. |
| Marketplace pull as adoption grows | Hold the line: no `qdo extension install <url>`. Extensions are local files or pip packages. PyPI is the registry; we don't run one. |
| Trust / supply chain on installable plugins | Same `scripts/check_deps.py` quarantine model as for runtime deps — entry-point plugins are scanned, new releases held 7 days. Local `.py` files prompt on first load. |

---

## Filter for whether to build this

Restating DIFFERENTIATION.md's "Filter for future changes" against this
proposal:

1. **Does this make the compounding loop tighter, cheaper, or more correct?**
   *Indirectly yes, only if scoped right.* A custom quality check feeds the
   same `quality → metadata → context` loop. A custom connector lets the loop
   apply to a database we don't ship support for. A custom command does not
   tighten the loop and is the riskiest hook to expose.
2. **Does it cost startup or install for users who don't use it?**
   *Should be no.* Lazy-load on first invocation; path-only enumeration at
   startup. Must be enforceable, e.g. a benchmark in `scripts/benchmark.py`
   that asserts cold-start with N=0..N=20 extensions present is constant.
3. **Does it require a running service?** No.
4. **Does it put an LLM call inside qdo?** No (and the SDK actively
   discourages it).
5. **Does it fragment the CLI surface?** *Risk: yes.* Mitigation: built-ins
   stay first-class in help, docs, and SKILL.md; extension-defined commands
   are visibly second-tier.

Net read: this clears the filter only if we hold the line on (1) and (5). The
seven hook types listed above are scoped specifically so most extensions feed
the loop instead of competing with it. If we built it and immediately
back-doored "user-defined first-class commands surfaced in the canonical
workflow," we'd have failed.

---

## Mini-plan if this gets promoted

Phased so each phase is independently shippable and the next is gated on
adoption signal from the previous.

**Phase E.1 — Discovery + Connector + QualityCheck (smallest credible slice).**
- `from querido.ext import qdo` SDK exposes `@qdo.connector` and
  `@qdo.quality_check`.
- Local-file discovery only. No entry-point plugin path yet.
- `qdo extension list / show / test`.
- One reference extension shipped per type under `docs/examples/extensions/`.
- SKILL.md gains a single short section pointing at scaffolding.

  Why this slice: connectors and quality checks are the two most-asked-for
  primitives qdo doesn't have, and both feed the loop rather than fragmenting
  it. They're the safest place to learn the SDK shape.

**Phase E.2 — Output format + Metadata field + Next-steps rule.**
- Adds the renderer, schema, and suggestion-graph hooks.
- `qdo extension scaffold <name> --type <kind>` lands.
- `qdo extension docs` prints the SDK reference (same content the agent
  reads).

**Phase E.3 — Command extension + Workflow step type.**
- The riskiest hooks. Only ship after E.1 + E.2 have real users and we've
  watched for fragmentation in eval / SKILL traces.
- Help output explicitly partitions Built-in vs Extension commands.

**Phase E.4 — Entry-point plugin path (`querido.extensions`).**
- Pip-installable extensions for team-shared use.
- Quarantine integration (`check_deps.py`).
- Bundle support: `qdo bundle export --include-extensions` lists extension
  fingerprints in the manifest, doesn't bundle the code itself (security).

**Non-goals across all phases:**
- No marketplace.
- No `qdo extension install <url>`.
- No hot-reload primitive (every invocation is fresh).
- No retroactive rewrite of built-ins as extensions.
- No promoted-workflow surface for extension-defined commands.

---

## Open questions

The questions worth holding open until there's signal:

1. **Naming.** "Extension" matches Pi and Datasette/VSCode. "Plugin" matches
   pytest. "Hook" matches click. We'd want one word, used consistently. Pi's
   word is the cleanest fit given the agent-authored framing.
2. **Trust prompt cadence.** First load? Every load? Hash-pinned? `~/.bashrc`
   model (load whatever's there) is honest but loose; pip-package model is
   stricter. Likely answer: prompt-on-first-load with `qdo extension trust`
   to silence; never prompt for entry-point plugins (the install was the
   signal).
3. **SDK versioning.** Extensions declare `qdo_sdk_version = 1`. How long do
   we hold breaking changes? Probably one major-version cycle.
4. **Bundle interaction.** Do bundles include extension *fingerprints* (so a
   teammate sees "this bundle expected `phone_format` quality check") or
   nothing? Including the code itself is a supply-chain hazard; including
   nothing leaves a bundle silently incomplete on import. Lean toward
   fingerprints + advisory message.
5. **Eval interaction.** Is the eval canonical-only (`QDO_EXT_DISABLED=1`),
   or do we eventually grade extensions too? Canonical-only for now;
   extension grading is its own future thing if we get there.
6. **Discovery cost ceiling.** A user with 50 local extensions should still
   see <50ms startup overhead. We'd want a benchmark, not a vibe.
7. **Where does this sit relative to MCP?** IDEAS.md keeps an MCP wrapper
   deferred. If we build extensions, MCP-as-extension is the cleanest path:
   ship MCP as one extension that exposes the qdo CLI surface, rather than
   as a parallel project.

---

## Verdict (research-grade, not a decision)

This is a **plausible** direction that survives the invariants *if* we hold
two specific lines:

- **Built-ins stay first-class.** No "everything is a plugin" rewrite.
- **No marketplace, ever.** Files or pip; we don't run a registry.

The most compelling argument for building it isn't user demand — qdo doesn't
have the user base yet to make plugin pull a real signal. It's the
**workplace-private** and **agent-authored** use cases. Both are about
preserving qdo's value in contexts where the main repo can't reach: code that
can't leave a corporate network, and ideas the user wants to try in an
afternoon without opening a PR.

The most compelling argument *against* is that we'd be solving a problem we
don't have yet, at the cost of a permanent maintenance surface. Workflows and
metadata already cover ~70% of "I want qdo to know my context." The remaining
30% is real but small, and a fork or a vendor-patch is a legitimate way to
solve it for now.

**Suggested next move (if anyone wants to move this from research to plan):**
prototype Phase E.1 (Connector + QualityCheck) on a branch as a feasibility
exercise, *without* SDK-level decorators — just hand-wired registration. If
adding a Postgres connector and a phone-format quality check both come in
under ~200 LOC each and feel natural against the existing connector Protocol,
the SDK is worth designing. If either feels grafted-on, the answer is "not
yet" and this doc gets a "rejected" status block at the top.

---

## References

- Armin Ronacher, *"Pi: The Minimal Agent Within OpenClaw"*, 2026‑01‑31 —
  [lucumr.pocoo.org/2026/1/31/pi/](https://lucumr.pocoo.org/2026/1/31/pi/)
- Pi extension docs —
  [github.com/badlogic/pi-mono/.../extensions.md](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md)
- Pragmatic Engineer, *"Building Pi, and what makes self-modifying software
  so fascinating"* —
  [newsletter.pragmaticengineer.com/p/building-pi-and-what-makes-self-modifying](https://newsletter.pragmaticengineer.com/p/building-pi-and-what-makes-self-modifying)
- qdo: [DIFFERENTIATION.md](../../DIFFERENTIATION.md), [IDEAS.md](../../IDEAS.md),
  [ARCHITECTURE.md](../../ARCHITECTURE.md), `src/querido/core/workflow/spec.py`
  (the existing-extension-shape that this proposal sits next to).
