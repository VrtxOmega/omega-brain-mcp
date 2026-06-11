#!/usr/bin/env bash
set -euo pipefail

detect_base_url() {
  if [[ -n "${OMEGA_BASE_URL:-}" ]]; then
    printf '%s\n' "$OMEGA_BASE_URL"
    return
  fi

  local candidates=("http://100.65.218.30:7700")
  if command -v ss >/dev/null 2>&1; then
    while IFS= read -r listen_addr; do
      [[ -z "$listen_addr" ]] && continue
      candidates+=("http://${listen_addr}:7700")
    done < <(ss -H -ltn 2>/dev/null | awk '
      $4 ~ /:7700$/ {
        addr = $4
        sub(/^\[/, "", addr)
        sub(/\]:7700$/, "", addr)
        sub(/:7700$/, "", addr)
        if (addr != "0.0.0.0" && addr != "::" && addr != "*" && addr !~ /:/) {
          print addr
        }
      }
    ' | sort -u)
  fi
  candidates+=("http://127.0.0.1:7700")

  local url
  for url in "${candidates[@]}"; do
    if curl -fsS --connect-timeout 1 --max-time 2 "$url/health" >/dev/null 2>&1; then
      printf '%s\n' "$url"
      return
    fi
  done

  printf '%s\n' "http://100.65.218.30:7700"
}

resolve_token() {
  local agent="${1:-hermes}"
  if [[ -n "${OMEGA_BRAIN_TOKEN:-}" ]]; then
    printf '%s\n' "$OMEGA_BRAIN_TOKEN"
    return
  fi
  local token
  token="$(python3 - "$agent" <<'PY'
import json, pathlib, sys
agent = sys.argv[1]
path = pathlib.Path.home() / ".omega-brain/agent_tokens.json"
if path.exists():
    data = json.loads(path.read_text())
    for token, name in data.items():
        if name == agent:
            print(token)
            break
PY
)"
  if [[ -n "$token" ]]; then
    printf '%s\n' "$token"
    return
  fi
  local token_file="${OMEGA_TOKEN_FILE:-$HOME/.omega-brain/network.token}"
  if [[ -f "$token_file" ]]; then
    cat "$token_file"
  fi
}

normalize_agent() {
  local a="${1,,}"
  case "$a" in
    anti-gravity|anti_gravity|"anti gravity") echo antigravity ;;
    windsurf|windswift) echo devin ;;
    *) echo "$a" ;;
  esac
}

send_message() {
  local to_agent="" topic="note" body="" source="hermes"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --to) to_agent="$(normalize_agent "$2")"; shift 2 ;;
      --topic) topic="$2"; shift 2 ;;
      --body) body="$2"; shift 2 ;;
      --source) source="$(normalize_agent "$2")"; shift 2 ;;
      *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
  done

  if [[ -z "$to_agent" || -z "$body" ]]; then
    echo "Usage: $0 send --to <agent> --body <text> [--topic <topic>] [--source <agent>]" >&2
    exit 2
  fi

  local base_url token payload
  base_url="$(detect_base_url)"
  token="$(resolve_token "$source")"
  if [[ -z "$token" ]]; then
    echo "Missing Omega Brain token for agent $source" >&2
    exit 1
  fi

  payload="$(python3 - "$to_agent" "$topic" "$body" "$source" <<'PY'
import json, sys
to_agent, topic, body, source = sys.argv[1:5]
print(json.dumps({
    "to_agent": to_agent,
    "topic": topic,
    "body": body,
    "source_agent": source,
}))
PY
)"

  curl -fsS -X POST "$base_url/api/send" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    --data "$payload"
}

inbox_for() {
  local agent="hermes"
  local limit=20
  local unread_only=true
  local mark_read=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --agent) agent="$(normalize_agent "$2")"; shift 2 ;;
      --limit) limit="$2"; shift 2 ;;
      --all) unread_only=false; shift ;;
      --mark-read) mark_read=true; shift ;;
      *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
  done

  local base_url token
  base_url="$(detect_base_url)"
  token="$(resolve_token "$agent")"
  curl -fsS -X POST "$base_url/api/inbox" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    --data "{\"source_agent\":\"$agent\",\"limit\":$limit,\"unread_only\":$unread_only,\"mark_read\":$mark_read}"
}

list_agents() {
  local base_url token
  base_url="$(detect_base_url)"
  token="$(resolve_token hermes)"
  curl -fsS -H "Authorization: Bearer $token" "$base_url/api/agents"
}

usage() {
  cat <<USAGE
Usage: $0 <send|inbox|agents> [options]

Commands:
  send   --to <agent> --body <text> [--topic <topic>] [--source hermes]
  inbox  --agent hermes [--limit <n>] [--all] [--mark-read]
  agents
USAGE
}

cmd="${1:-}"
shift || true
case "$cmd" in
  send) send_message "$@" ;;
  inbox) inbox_for "$@" ;;
  agents) list_agents ;;
  *) usage ; exit 2 ;;
esac