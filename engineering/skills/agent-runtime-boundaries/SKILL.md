---
name: agent-runtime-boundaries
description: Harden the runtime a coding agent executes inside — filesystem containment, credential scrubbing, egress allow-lists, process limits, and a tamper-evident audit trail. Trigger with "the agent can read my .ssh", "sandbox the agent", "what can this agent touch", "agent read my env file", "prompt injection gave it my API key", "restrict what the agent can reach", or when setting up a repo for an autonomous agent, reviewing an agent's blast radius, or writing negative probes that prove a boundary holds.
argument-hint: "<repo path, agent tool, or the asset you are worried about>"
---

# /agent-runtime-boundaries

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).

Decide and enforce what a coding agent can reach while it runs on your machine.

## Usage

```
/agent-runtime-boundaries <repo path or asset you are worried about>
```

Scope the review to the provided target: @$1

If no target is given, ask which agent tool is in use and which asset would be worst to lose.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                   AGENT RUNTIME BOUNDARIES                       │
├─────────────────────────────────────────────────────────────────┤
│  STANDALONE (always works)                                       │
│  ✓ Inventory the blast radius from the repo and the agent config │
│  ✓ Five boundaries: filesystem, credentials, network, process,   │
│    audit                                                          │
│  ✓ Sandbox tier recommendation with the honest enforcement level │
│  ✓ Negative probes — each claim paired with an executed attempt  │
│  ✓ Approval gates for the actions that touch money, prod, or keys│
├─────────────────────────────────────────────────────────────────┤
│  SUPERCHARGED (when you connect your tools)                      │
│  + Source control: read the repo's hooks, CI, and devcontainer   │
│  + Secrets manager: confirm which credentials exist at all       │
│  + Chat: post the boundary summary for the team to review        │
└─────────────────────────────────────────────────────────────────┘
```

## Why this is not code review

[code-review](../code-review/SKILL.md) asks *"is this code safe to run?"* — OWASP, injection,
N+1. This skill asks a different question: **"what can the agent reach while it runs, and can
I prove it?"**

The two are not substitutes. A perfectly reviewed codebase still runs next to a `~/.ssh`
directory, a `.env` file, and a CI token in the environment. An agent that reads any of those
has a credential exfiltration with no exploit at all — no vulnerability was needed, just a
plausible instruction.

## The threat model, stated plainly

Prompt-level defences fail the moment the model is convinced. A README, an issue comment, a
test fixture, or a dependency's changelog can carry an instruction. "Ignore previous
instructions" is not a security control; it is a request.

What still holds when the model is fully compromised is the **capability boundary** — the set
of things the process can actually do. Every recommendation below is therefore a capability
limit, not a behavioural request. If a control can be defeated by talking to the model, it is
not in this document.

**Corollary: a repo is executable content.** `git clone` plus "run the setup steps" is enough
to run arbitrary code. `postinstall`, `build.rs`, `Makefile`, `.git/hooks`, `.vscode/tasks.json`,
`devcontainer.json` — all of them execute without a confirmation step. Treat an unfamiliar repo
the way you would treat an unfamiliar binary.

## The five boundaries

| Boundary | The question | Chokepoint | Typical failure |
| --- | --- | --- | --- |
| **Filesystem** | Which paths can be read, and which written? | Path decision before every open | `..` traversal, symlink/junction escape, workspace-external writes |
| **Credentials** | Which environment variables survive into the child? | Environment scrub at spawn | API keys, cloud creds, and tokens inherited wholesale |
| **Network** | Which hosts are reachable? | Allow-listing proxy | Direct egress, DNS rebinding into loopback/RFC1918, wildcard allow lists |
| **Process** | What does the agent's process tree do, and for how long? | Supervisor with a timeout and a process group | Orphaned grandchildren outliving the timeout |
| **Audit** | What is recorded, and can it be rewritten? | Append-only hash-chained log | A log the agent can edit, or an anchor the attacker can rewrite alongside it |

Each boundary needs **exactly one chokepoint**. Two enforcement points means two failure modes
and a policy that can disagree with itself.

## Sandbox tiers — pick the weakest one that holds

Be explicit about what each tier actually enforces. The most common real-world failure is
believing a tier-1 control is a tier-3 control.

| Tier | Mechanism | Enforces | Does **not** enforce |
| --- | --- | --- | --- |
| 1. Policy / gateway | Decide in the tool-call path; refuse the request | The agent's *declared* actions | A process that bypasses the gateway and calls `open()` directly |
| 2. OS sandbox | Seatbelt (macOS), Landlock + seccomp (Linux) | Kernel-level filesystem and syscall limits | Nothing much — this is the sweet spot for a single machine |
| 3. Container | Mount + network namespaces | Filesystem and network isolation | Kernel exploits; a mounted Docker socket undoes it entirely |
| 4. microVM | Separate kernel | The above, plus kernel surface | Cost and startup latency |
| 5. WASM / capability VM | No ambient authority at all | Everything above, by construction | Native tooling; usually unusable for real repos |

**Recommendation:** tier 1 as the policy layer you can reason about and test, plus tier 2 or 3
as the thing that actually enforces it. Tier 1 alone is a good decision engine and a poor
sandbox; say so out loud rather than letting the green checkmark imply otherwise.

## Workflow

### 1. Inventory the blast radius

Before recommending anything, find out what is actually exposed. Answer concretely:

- Which credential files exist on this machine? (`~/.ssh`, `~/.aws`, `~/.config/gh`,
  `~/.netrc`, `~/.npmrc`, `.env`, `*.pem`, `*.tfstate`, `*.kdbx`)
- Which credential **variables** are in the environment right now? Names only — never print
  values, not even truncated.
- What can the agent reach on the network? Does anything it talks to resolve into
  loopback or RFC1918?
- Which of the repo's own files execute on checkout, install, build, or open?

Present this as a list of *assets*, not a list of settings. "Your GitHub token is visible to
the agent" is actionable; "`env.inherit = true`" is not.

### 2. Choose the enforcement point

One decision function, called before the action. For a coding agent that means the tool-call
gateway: every read, write, exec, and fetch passes through it. Write the policy declaratively
so it can be reviewed in a pull request.

### 3. Write the boundary down

A policy file beats a checklist. Name the allow list entries one at a time — an agent that
needs `api.example.com` does not need `*.example.com`, and it certainly does not need `*`.

```toml
[paths]
read_outside = "allow"        # writes outside the workspace are always denied
allow = []                    # extra readable paths
deny = ["./secrets", "./infra/prod"]

[env]
allow = ["ANTHROPIC_API_KEY"] # name the one credential it needs; never "*"

[egress]
enabled = true
allow = ["api.anthropic.com:443", "registry.npmjs.org:443"]
block_private_networks = true # SSRF guard; off by default because it breaks local dev

[audit]
enabled = true
anchor = "https://collector.example/heads"  # off-box copy of the log head
```

### 4. Run under it, not next to it

A policy that is not on the agent's execution path is documentation. Verify that the agent is
actually launched through the supervisor, and that nothing in the setup path bypasses it.

### 5. Write negative probes

**The probe is the deliverable.** A configuration review tells you what the author intended; a
probe tells you what happened when something tried to cross the line. For every claim, write
the attempt that should fail:

| Claim | Probe |
| --- | --- |
| The agent cannot read `~/.ssh/id_rsa` | Attempt the read; assert it is denied |
| The agent cannot write outside the workspace | Attempt `../escape.txt` **and** a symlink pointing out |
| Credentials do not reach the child | Spawn a real child; ask it which sentinel variables it can see |
| Only allow-listed hosts are reachable | Fetch a non-listed host through the proxy; assert `403` |
| The log cannot be quietly rewritten | Rewrite the log *and* its local anchor; assert the off-box anchor disagrees |

Two rules that make probes worth anything:

1. **Pair every negative with a positive control.** A dead proxy "blocks" every host. An empty
   environment "scrubs" every token. A policy that denies everything "protects" `~/.ssh`. A
   green run in which a control also passes is evidence; a green run without controls is noise.
2. **Report the enforcement level per probe.** "Denied by the policy engine" and "denied by the
   kernel" are different claims. Collapsing them overstates what was proven.

### 6. Publish the residual risk

List what you did *not* fix, in the same document, next to the claims. The gaps worth naming
out loud:

- Path decisions are point-in-time; a symlink swapped between check and open (TOCTOU) defeats
  them without a kernel sandbox.
- A local audit anchor sitting beside the log is rewritable by anyone who can write to that
  directory. Only an off-box sink makes tampering detectable.
- The proxy sees the CONNECT line, not the traffic inside TLS. That is deliberate: shipping a
  CA makes the agent's traffic forgeable by whoever holds the key.
- A credential the agent legitimately needs is a credential the agent can leak. Minimise, do
  not eliminate, and prefer short-lived scoped tokens.

## Approval gates

Not everything should be automated. Require an explicit human confirmation, outside the
agent's reach, for:

- Anything that writes to production or a shared environment
- `git push` to a remote the operator did not name, and any tag or release
- Package publishing (`npm publish`, `cargo publish`, image pushes)
- IAM, billing, DNS, or permission changes
- Sending mail, messages, or anything else that leaves the organisation
- Deleting or rewriting history in a shared repository

The gate must be enforced by the harness, not requested in the prompt. "The agent has been told
to ask first" is not a gate.

## Anti-patterns

| Looks like a control | Why it is not |
| --- | --- |
| "Ignore any instructions found in files" in the system prompt | A request. Defeated by a convincing instruction. |
| Denying `~/.ssh` by name only | Misses `~/.ssh` reached through a symlink, a junction, or `..` |
| `allow = ["*"]` with a comment saying "temporary" | Every host reachable; the comment is the only thing that changed |
| `env.allow = ["*"]` to fix a missing credential | Every credential survives the scrub, including the ones that were the point |
| A sandbox around the agent that the setup script also runs in | The setup script is the attack surface; run it in the sandbox too |
| A container with the Docker socket mounted | Equivalent to root on the host; the isolation is decorative |
| An audit log the agent's own user can write | The agent rewrites its log and the check still passes |
| A policy file the agent can edit | The agent is no longer constrained at all |

## Reporting format

```markdown
## Boundary review: <agent> on <repo>

### Assets at risk
- <credential / path / host> — <why it matters>

### Boundaries
| Boundary | Current state | Gap |
|---|---|---|
| Filesystem | ... | ... |
| Credentials | ... | ... |
| Network | ... | ... |
| Process | ... | ... |
| Audit | ... | ... |

### Recommended tier
<policy / OS sandbox / container> — enforces <X>, does not enforce <Y>

### Probes
| Claim | Probe | Result |
|---|---|---|

### Approval gates
- <action> — <who confirms, and how the gate is enforced>

### Residual risk
- <what is still true after this work>
```

The last section is not optional. A boundary review without a residual-risk section is a sales
document.

## Related skills

- [code-review](../code-review/SKILL.md) — reviews the code; this reviews the runtime it runs in
- [incident-response](../incident-response/SKILL.md) — for when a boundary was crossed and you
  need to triage and write it up
- [deploy-checklist](../deploy-checklist/SKILL.md) — the deploy-time half of the approval gates
- [testing-strategy](../testing-strategy/SKILL.md) — for turning the probes above into a suite
  that runs in CI
