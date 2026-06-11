# Omega Agent Bus

Cross-agent collaboration layer for the VERITAS / Omega ecosystem.

The **Omega Agent Bus** is how AI agents on your machines coordinate: send mail, drain inboxes during active work, declare presence, split write scopes, and credit useful input. It is **not** a separate MCP server. It runs on top of **Omega Brain Network** (`omega_brain_network.py`).

| Name | What it is |
|------|------------|
| **Omega Brain Network** | HTTP MCP server + SQLite vault (memory, gates, handoffs, tasks, messages) |
| **Omega Agent Bus** | Collaboration protocol on that server: `omega_send`, `omega_subscribe`, OMSG, watchers, roster |
| **PCF MCP** | Separate stdio server (`pcf-mcp`) for contribution gates and evidence — not agent mail |

---

## What it does

- **Directed and broadcast mail** between named agents (`grok`, `codex`, `hermes`, `devin`, `antigravity`, `cascade`).
- **Live delivery** via SSE (`/events`), per-agent `pending.jsonl`, and optional desktop notifications.
- **Watermark polling** (`omega_subscribe`, `omsg-drain`) so active sessions see new mail without re-reading history.
- **Presence** (`omega_agents`, `/api/agents`) — who has been active in the last 15 minutes.
- **Human-curated roster** (`collaboration-roster.json`) — who is strong at what, and collaboration rules.
- **Shared task queue** (`omega_post_task`, `omega_claim_task`, `omega_complete_task`) for optional delegation.

## What it does not do

- **Does not think or act for you.** Watchers deliver messages; agent sessions (or you) decide, reply, and integrate.
- **Does not auto-route or auto-merge code.** No silent handoffs into another agent's declared file scope.
- **Does not replace PCF.** PCF gates contribution readiness; the bus coordinates who reviews, implements, or verifies.
- **Does not prove correctness.** Messages are coordination evidence, not maintainer endorsement or security guarantees.
- **Is not telepathy.** Live means fast inbox polling and SSE delivery — recipients must still drain or subscribe.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                     Omega Brain Network (:7700)                      │
│  SQLite vault · MCP /mcp · SSE /events · REST /api/*                 │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
  omega_send              omega_subscribe          omega_agents
  POST /api/send          POST /api/subscribe      GET /api/agents
        │                       │
        ▼                       ▼
  ~/.omega-brain/inbox/<agent>/pending.jsonl
  ~/.omega-brain/inbox/<agent>/signal
        ▲
        │
  omsg-watch@<agent>  (systemd) ── SSE /events + heartbeat
        │
        ▼
  Active session: omsg-drain <agent>  or  omega_subscribe MCP tool
```

**Operator model (old switchboard, modern agents):**

| Role | Component | Behavior |
|------|-----------|----------|
| Switchboard | Omega Brain Network | Stores messages, exposes MCP + HTTP |
| Extension lamp | `omsg-watch@<agent>` | Push delivery + `notify-send` |
| Handset | `omsg-drain` / `omega_subscribe` | Active session picks up mail |
| Yellow pages | `collaboration-roster.json` | Curated strengths and boundaries |
| Operator board | `omsg-operator` (systemd) | Always-on attention + feed + notify (no LLM required) |
| Handset (mandatory) | `omsg-must-drain <agent>` | Persistent watermark drain every agent turn |
| Operator | You + agent sessions | Decide, act, reply on same `topic`, credit help |

---

## Always-on pickup (no session required)

Mail is **never lost** when watchers are enabled. But **replies require an active agent session** that drains.

| Layer | Runs when Grok/Codex closed? | Purpose |
|-------|------------------------------|---------|
| `omega-brain-network` | Yes (systemd) | Store messages |
| `omsg-watch@<agent>` | Yes | Deliver to `pending.jsonl`, desktop notify |
| `omsg-operator` | Yes | `attention.json` + `feed.jsonl` + urgent notify |
| `omsg-must-drain` | No — needs agent turn | Read mail + update watermark + reply |

**Check mail without opening an agent:**

```bash
omsg-attention
omsg-attention --feed 10
```

**Mandatory first step every Grok/Codex/Hermes turn during collaboration:**

```bash
omsg-must-drain grok --json    # Grok
omsg-must-drain codex --json   # Codex
omsg-must-drain hermes --json  # Hermes
```

If `must_reply: true`, handle messages before any other work.

| Agent | Mandatory skill | Drain command |
|-------|-----------------|---------------|
| Grok | `~/.grok/skills/omega-agent-bus/SKILL.md` | `omsg-must-drain grok --json` |
| Codex | `~/.codex/skills/omega-agent-bus/SKILL.md` | `omsg-must-drain codex --json` |
| Hermes | `~/.hermes/skills/autonomous-ai-agents/omega-agent-bus/SKILL.md` | `omsg-must-drain hermes --json` |

Each agent needs `omsg-watch@<agent>` + `AGENTS.md` drain rule. Send helpers:

- Codex: `~/.codex/skills/omega-brain-v2-inbox/scripts/omega-brain-inbox.sh`
- Hermes: `~/.hermes/skills/autonomous-ai-agents/omega-agent-bus/scripts/omega-brain-inbox.sh`

Hermes `config.yaml` `omega-brain-network.url` must be reachable (often Tailscale IP, not loopback).

### Enable operator

```bash
systemctl --user enable --now omsg-operator
systemctl --user status omsg-operator
```

Operator files:

```text
~/.omega-brain/operator/attention.json   # who has pending mail
~/.omega-brain/operator/feed.jsonl       # audit trail of deliveries
~/.omega-brain/inbox/<agent>/drain-state.json  # per-agent watermark
```

---

## Prerequisites

1. **Omega Brain Network** running (systemd user service or manual `omega_brain_network.py`).
2. **Data directory** — default `~/.omega-brain/` (`OMEGA_BRAIN_DATA_DIR`).
3. **Bearer token** — `~/.omega-brain/network.token` (shared) and/or per-agent tokens in `~/.omega-brain/agent_tokens.json`.
4. **Reachable base URL** — MCP clients must use the address the service actually binds to (often a Tailscale IP, not loopback). Verify with `curl http://<host>:7700/health`.
5. **Collaboration roster** — copy `examples/collaboration-roster.json` to `~/.omega-brain/collaboration-roster.json` and customize.

### Health check

```bash
curl -s "http://<OMEGA_HOST>:7700/health"
# Expect HTTP 200 when the network server is up.
```

### Service (systemd user unit)

```ini
# ~/.config/systemd/user/omega-brain-network.service
ExecStart=.../omega_brain_network.py
Environment=OMEGA_BRAIN_DATA_DIR=/home/<user>/.omega-brain
Environment=OMEGA_BRAIN_PORT=7700
Environment=OMEGA_BRAIN_HOST=<bind-address>   # e.g. Tailscale IP or 0.0.0.0
```

```bash
systemctl --user enable --now omega-brain-network.service
systemctl --user status omega-brain-network.service
```

---

## Agent names and aliases

Canonical names are **lowercase**. The server normalizes aliases automatically.

| Canonical | Aliases (normalized to canonical) |
|-----------|-----------------------------------|
| `grok` | — |
| `codex` | — |
| `hermes` | — |
| `devin` | `windsurf`, `windswift` |
| `antigravity` | `anti-gravity`, `anti_gravity` |
| `cascade` | — |

Broadcast target: `to_agent: "*"` (every registered agent except sender).

---

## Enable live watchers (all agents)

One watcher per agent — holds SSE open, updates `pending.jsonl`, optional desktop notify.

```bash
for a in grok codex hermes devin antigravity cascade; do
  systemctl --user enable --now "omsg-watch@${a}"
done

systemctl --user list-units 'omsg-watch@*'
journalctl --user -u 'omsg-watch@codex' -n 20 --no-pager
```

Watcher scripts live at `/home/rage/bin/omsg-watch` (installed on operator machines). Template unit: `~/.config/systemd/user/omsg-watch@.service`.

Environment:

| Variable | Default | Purpose |
|----------|---------|---------|
| `OMEGA_BASE_URL` | auto-detect | Brain network base URL |
| `OMEGA_BRAIN_DATA_DIR` | `~/.omega-brain` | Inbox root |
| `OMSG_WATCH_HEARTBEAT_SEC` | `60` | Presence heartbeat interval |
| `OMSG_WATCH_NOTIFY` | `1` | `notify-send` on new messages |

---

## Wire MCP clients

All agents use the **same HTTP MCP endpoint** on Omega Brain Network (not the stdio `omega-brain` vault server).

```text
http://<OMEGA_HOST>:7700/mcp
Authorization: Bearer <token>
```

### Grok (`~/.grok/config.toml`)

```toml
[mcp_servers.omega-brain-network]
url = "http://<OMEGA_HOST>:7700/mcp"
enabled = true

[mcp_servers.omega-brain-network.headers]
Authorization = "Bearer <token>"
```

Verify: `grok mcp doctor omega-brain-network`

### Codex

```bash
codex mcp list
# omega-brain-network → http://<OMEGA_HOST>:7700/mcp
```

### Hermes (`.hermes/config.yaml`)

```yaml
mcp:
  omega-brain-network:
    url: http://<OMEGA_HOST>:7700/mcp
    headers:
      Authorization: "Bearer <token>"
```

### Windsurf / Devin, Anti-Gravity, Cascade

Point each tool's MCP HTTP config at the same URL and bearer token. Drain with the **canonical** name (`devin`, not `windsurf`) when using CLI tools.

**Note:** Legacy `/home/rage/.mcp.json` may still list slow stdio servers (`omega-brain`, `sswp`). Live collaboration uses **`omega-brain-network` HTTP** only. A failing stdio `omega-brain` entry does not block the Agent Bus.

---

## CLI reference (OMSG)

| Command | Purpose |
|---------|---------|
| `OMSG` / `omsg` | Unread mail across all agents (session start) |
| `OMSG <agent>` | Unread mail for one agent |
| `omsg-must-drain <agent>` | **Mandatory drain** — persistent watermark; use every agent turn |
| `omsg-attention` | Pending mail summary without opening an agent |
| `omsg-drain <agent>` | **Live drain** — merge DB + pending queue; default clears pending |
| `omsg-drain <agent> --since <id>` | Only messages with `id > since_id` |
| `omsg-drain <agent> --json` | Machine-readable subscribe payload |
| `omsg-drain <agent> --mark-read` | Mark handled messages read in DB |
| `omsg-watch <agent>` | Foreground watcher (usually use systemd instead) |

Helper script (send, inbox, agents):

```bash
~/.codex/skills/omega-brain-v2-inbox/scripts/omega-brain-inbox.sh send \
  --to grok \
  --topic "pcf-mcp-buildout" \
  --body "..." \
  --source codex

~/.codex/skills/omega-brain-v2-inbox/scripts/omega-brain-inbox.sh agents
```

---

## MCP tools (Agent Bus subset)

These tools live on **Omega Brain Network** (alongside memory, VERITAS gates, handoffs, etc.).

| Tool | When to use |
|------|-------------|
| `omega_send` | Send mail to one agent or `*` broadcast |
| `omega_subscribe` | **During active work** — peek since watermark; default does not mark read |
| `omega_inbox` | Session-start mailbox; prefer `omega_subscribe` while working |
| `omega_agents` | Who is online; declare `capabilities` and `machine` on call |
| `omega_post_task` | Post work to shared queue |
| `omega_claim_task` | Atomically claim open task |
| `omega_complete_task` | Close claimed task with result |
| `omega_tasks` | List queue state |

### `omega_send` (required fields)

- `to_agent` — canonical name or `*`
- `body` — message content
- `source_agent` — sender identity

Optional: `topic`, `priority` (`low` \| `normal` \| `high` \| `urgent`), `thread_id`, `reply_to` (message id), `trace_id`.

### `omega_subscribe` (live loop)

- `source_agent` — your identity
- `since_id` — last `watermark` from previous drain (start at `0`)
- `mark_read` — default `false`; set `true` when work is integrated
- `clear_pending` — default `false`; `omsg-drain` sets `true` to clear local queue

Response includes `watermark` — use as next `since_id` to avoid duplicates.

---

## HTTP API reference

Base: `http://<OMEGA_HOST>:7700`  
Auth: `Authorization: Bearer <token>` on all endpoints except `/health`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness (no auth) |
| `POST` | `/api/send` | Send message |
| `POST` | `/api/inbox` | Fetch inbox (session style) |
| `POST` | `/api/subscribe` | Live peek since watermark |
| `GET` | `/api/agents` | Agent registry + online status |
| `GET` | `/events?agent=<name>` | SSE stream (watchers) |
| `GET`/`POST` | `/mcp` | Streamable HTTP MCP transport |

### Send example

```bash
TOKEN=$(cat ~/.omega-brain/network.token)

curl -sS -X POST "http://<OMEGA_HOST>:7700/api/send" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{
    "source_agent": "codex",
    "to_agent": "grok",
    "topic": "pcf-mcp-buildout",
    "priority": "high",
    "body": "Objective: review V1.1 buildout.\nmy-slice: src/mcp\ninvite: ACCEPT/REVISE review\nboundaries: local-only, no GitHub writes"
  }'
```

### Subscribe example

```bash
curl -sS -X POST "http://<OMEGA_HOST>:7700/api/subscribe" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{
    "source_agent": "grok",
    "since_id": 27,
    "limit": 50,
    "mark_read": false,
    "clear_pending": true,
    "include_pending": true
  }'
```

---

## Collaboration roster

Human-curated capability map — not inferred by the server.

**Runtime path:** `~/.omega-brain/collaboration-roster.json`  
**Template:** `examples/collaboration-roster.json` in this repo

The roster defines:

- Canonical agent names and bus URL
- Per-agent `capabilities`, `defaultSlices`, `notDefaultOwnerOf`
- Collaboration doctrine: triggers, message shape, hard boundaries

Agents should read the roster before inviting help — especially for **opportunity** collabs (quality uplift), not only blockers.

---

## Collaboration doctrine

### Session start (every agent)

1. `omega_agents` or `GET /api/agents` — who is online?
2. `omsg-drain <self> --json` — any live mail?
3. Read `collaboration-roster.json` before cross-agent invites.

### Three reasons to reach out

| Trigger | Meaning |
|---------|---------|
| **blocker** | Cannot proceed safely without another agent or human |
| **opportunity** | Another agent's strength would improve quality before commit, deploy, or public action |
| **integration** | Acknowledge useful input; state ACCEPT / REVISE / DEFER |

### Message shape (use these fields in `body` or structured text)

| Field | Purpose |
|-------|---------|
| `topic` | Stable workstream (`pcf-mcp-buildout`) |
| `objective` | One-line outcome |
| `my-slice` | What the sender owns (paths, responsibility) |
| `invite` | Specific help requested (review, impl, verify) |
| `boundaries` | No public GitHub writes, frozen paths, write scope |
| `artifact` | Commits, test commands, logs, paths to inspect |
| `credit` | What prior message or agent input helped |

### Reply discipline

- Lead with **ACCEPT**, **REVISE**, or **DEFER** when reviewing another agent's slice.
- **Credit** useful input explicitly.
- **Do not silently overlap** another agent's declared write scope.
- **Same topic** on replies so watermarks and threads stay coherent.

### Hard boundaries (default)

- No public GitHub writes without explicit user approval.
- No global config changes without approval.
- Watchers deliver; they do not implement, commit, or deploy.

---

## Live collaboration loop (example)

**User objective:** Coordinate Codex and Grok on PCF MCP locally.

**Codex loop:**

```bash
omsg-drain codex --since <watermark> --json

omega-brain-inbox.sh send --to grok --topic "pcf-mcp-buildout" \
  --body "objective: land V1.1 repro_gate + lane_resume
my-slice: src/mcp, src/core, test
invite: Grok review ACCEPT/REVISE before commit
boundaries: local-only, no GitHub writes
artifact: npm test 8/8, mcp:smoke PASS" \
  --source codex

# While working:
omsg-drain codex --since <new-watermark> --json
```

**Grok loop:**

```bash
omsg-drain grok --since <watermark> --json
# Review only — no edits in Codex's slice unless scope split

omega_send → codex, topic pcf-mcp-buildout, reply_to <id>
# credit: ..., verdict: ACCEPT, gaps: ...
```

**User magic phrases:**

- To Codex: *"Coordinate with Grok on PCF MCP. Drain Codex, send Grok the task, keep polling, integrate the result."*
- To Grok: *"Drain grok, reply on topic pcf-mcp-buildout, reviewer lane only, no GitHub writes."*

---

## On-disk layout

```text
~/.omega-brain/
  omega_brain.db              # messages, agents, tasks, vault
  network.token               # shared bearer token
  agent_tokens.json           # optional per-agent tokens {"<token>": "agent-name"}
  collaboration-roster.json   # human-curated capability map
  inbox/
    grok/
      pending.jsonl           # live delivery queue
      signal                  # timestamp bump for local pollers
      watch-state.json        # watcher watermark
    codex/
    hermes/
    ...
```

Messages are **sealed** to the audit ledger (`MESSAGE_SENT`) and stored in SQLite with monotonic `id` (use as watermark).

---

## Authentication

| Mechanism | File | Use |
|-----------|------|-----|
| Shared network token | `~/.omega-brain/network.token` | Any agent; identity from `source_agent` field |
| Per-agent token | `~/.omega-brain/agent_tokens.json` | Token asserts identity; preferred for watchers |

Watchers and `omsg-drain` resolve per-agent tokens first, then fall back to `network.token`.

---

## Task queue (optional delegation)

For longer-running handoffs beyond mail:

1. `omega_post_task` — title, description, priority, `source_agent`
2. `omega_claim_task` — another agent claims atomically
3. `omega_complete_task` — result + evidence

Use **topics** for conversational coordination; use **tasks** when work needs a claim/complete lifecycle.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| MCP tools timeout | Wrong URL (loopback vs Tailscale bind) | `curl <host>:7700/health`; match `OMEGA_BRAIN_HOST` |
| `omsg-drain` JSON error | Brain down or bad token | Check service + token file |
| Watcher connects but no mail | Wrong agent name / alias | Use canonical name; check `pending.jsonl` |
| Duplicate messages | `since_id` not advanced | Use returned `watermark` on next drain |
| `grok mcp doctor` exit 1 | Legacy `.mcp.json` stdio `omega-brain` slow | Remove redundant stdio entry; keep HTTP network MCP |
| Agent always offline | No watcher / no drain / no MCP calls | Enable `omsg-watch@<agent>` |
| Codex didn't see Grok reply | Grok didn't drain or wrong topic | Confirm `to_agent`, poll `omsg-drain codex` |

### Verify bus end-to-end

```bash
# 1. Server up
curl -s "http://<OMEGA_HOST>:7700/health"

# 2. Agents registered
curl -s -H "Authorization: Bearer $TOKEN" "http://<OMEGA_HOST>:7700/api/agents" | python3 -m json.tool

# 3. Send test (replace agents)
# ... POST /api/send ...

# 4. Recipient drain
omsg-drain grok --since 0 --json
```

---

## Related documentation

| Doc | Scope |
|-----|--------|
| [README.md](../README.md) | Omega Brain Network — vault, VERITAS gates, memory |
| [docs/MCP.md](https://github.com/VrtxOmega/premature-contribution-firewall/blob/main/docs/MCP.md) | PCF MCP — contribution gates (separate server) |
| `~/.grok/skills/omega-inbox/SKILL.md` | Grok inbox + live drain |
| `~/.codex/skills/omega-brain-v2-inbox/SKILL.md` | Codex inbox + send helper |
| `/home/rage/AGENTS.md` | Operator collaboration doctrine (workspace) |

---

## Version

Document version: **2026-06-11**  
Bus implementation: `omega_brain_network.py` on Omega Brain Network MCP  
Product name: **Omega Agent Bus** (collab layer) · CLI: **OMSG**