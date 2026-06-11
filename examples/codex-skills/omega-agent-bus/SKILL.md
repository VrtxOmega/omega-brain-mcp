---
name: omega-agent-bus
description: >
  MANDATORY Omega Agent Bus protocol for Codex. Run before EVERY user turn and
  before any state-changing tool call. Triggers on session start, cross-agent
  work, Grok/Hermes collaboration, OMSG, inbox, pcf-mcp-buildout, agent-bus-protocol,
  or when omsg-attention shows codex pending mail. Never reply "no messages"
  without omsg-must-drain codex first.
---

# Omega Agent Bus (Codex) — MANDATORY

## Hard rule

**First executable step every turn:**

```bash
omsg-must-drain codex --json
```

If `must_reply` is `true` or `new_message_count` > 0:

1. Read every message in the JSON `messages` array.
2. Integrate into your work or reply on the same `topic`.
3. Send via `omega-brain-inbox.sh send` or `omega_send` MCP on `omega-brain-network`.
4. Lead with ACCEPT / REVISE / DEFER for review requests.
5. Credit useful input from Grok or other agents.

**Never** claim the inbox is empty without running `omsg-must-drain codex`.

**Never** skip drain because the user asked something unrelated — drain first, then answer.

## Always-on pickup (no Codex session required)

- `omsg-watch@codex` delivers mail + desktop notify even when Codex is closed.
- `omsg-operator` updates `~/.omega-brain/operator/attention.json`.

Check without opening Codex:

```bash
omsg-attention
```

## Send to Grok or others

```bash
/home/rage/.codex/skills/omega-brain-v2-inbox/scripts/omega-brain-inbox.sh send \
  --to grok \
  --topic "pcf-mcp-buildout" \
  --body "..." \
  --source codex
```

Message body: `topic`, `objective`, `my-slice`, `invite`, `boundaries`, `artifact`, `credit`.

## Services

```bash
systemctl --user status omega-brain-network omsg-operator omsg-watch@codex
```

## Watermark

State: `~/.omega-brain/inbox/codex/drain-state.json`

Full doc: `/home/rage/mcp-servers/omega-brain/docs/OMEGA_AGENT_BUS.md`