---
name: sonos
description: Control Sonos speakers, playback, queues, groups, and music discovery on your local network.
metadata:
  status: ready
  cli_binary: sonos
---

# sonos CLI

A local Sonos CLI for discovery, playback control, grouping, queue operations, and Spotify/YouTube media playback. You must target a reachable speaker (usually via `--ip`, since UDP/multicast discovery is unreliable in this sandbox).

## Namespaces

| Group | Controls | Notes |
| ----- | -------- | ----- |
| `auth` | service authentication helpers | For Spotify-related SMAPI flows |
| `discover` | speaker discovery | Often replaced by direct IP in this environment |
| `status` | now/playing state | Read-only playback metadata |
| `play`, `pause`, `stop`, `next`, `prev` | transport | Basic transport controls |
| `volume`, `mute` | output level and mute | Group-level and speaker-level variants |
| `open`, `enqueue`, `play-uri`, `play-url`, `play youtube/spotify` | queueing and playback start |
| `queue` | queue content management | List, play, remove, clear |
| `search`, `smapi` | music lookup | Spotify via web API or Sonos SMAPI |
| `group` | multi-speaker grouping | join/leave/party/solo and group volume/mute |
| `favorites` | Sonos favorites | list/play by title or index |
| `scene` | room+group presets | save/list/apply/delete |
| `config`, `linein`, `tv`, `watch` | local config / source routing | Optional/advanced |

## Discovery

Known IDs and names for this workspace are in `tools.md`. Use them if present; otherwise discover:

```bash
sonos discover
sonos status
sonos status --ip <ip>
sonos queue list
```

The sandbox is on Docker NAT; Sonos discovery/multicast often fails here, so use:

```bash
sonos status --ip 192.168.178.68
sonos queue list --ip 192.168.178.68
```

## Common operations

```bash
sonos discover [--all]
sonos status
sonos status --ip <ip>
sonos stop
sonos play
sonos pause
sonos next
sonos prev
sonos mute <on|off|toggle|get>
sonos volume get
sonos volume set <0-100>

sonos open <spotify-uri-or-link>
sonos enqueue <spotify-uri-or-link> [--next] [--title <text>]
sonos play-uri <uri>
sonos play-url <url>
sonos play spotify <query>
sonos search spotify <query>
sonos smapi services
sonos smapi search <query> --service <service-name> [--category <category>]

sonos queue list
sonos queue play <1-based-position>
sonos queue remove <1-based-position>
sonos queue clear

sonos group status
sonos group join --to <room-or-ip>
sonos group unjoin
sonos group solo
sonos group dissolve
sonos group volume get
sonos group volume set <0-100>

sonos favorites list
sonos favorites open <title>
sonos favorites open --index <1-based-index>

sonos scene list
sonos scene save <name>
sonos scene apply <name>
sonos scene delete <name>

sonos config get
sonos config set <key> <value>
sonos config path
```

## Exceptions

- In this environment use `<ip>` directly; `--name` defaults to `"Sonos Era 100"` from config.
- `sonos status` without `--ip` relies on discovery and can fail with `no speakers found`.
- `search spotify` needs `--client-id` and `--client-secret` (or corresponding env vars).
- `smapi search` is index-aware: `--index` and `--open`/`--enqueue` use 1-based indices.
- Queue/play/remove positions are 1-based (`sonos queue play 1` is first item).
- `group join`/`party` require `--to <room-or-ip>` and a target speaker context via `--name/--ip`.
- `play spotify` uses SMAPI query index as 0-based.
- `volume set` and `group volume set` expect integer `0` to `100`.
- Use `--format json` only when a script consumes output.

## Verification

```bash
sonos status --ip <ip>
sonos queue list --ip <ip>
sonos volume get --ip <ip>
sonos group status --ip <ip>
sonos favorites list --ip <ip>
sonos scene list --ip <ip>
```

## Failure behavior

Common failures:

- `Error: no speakers found` / `try increasing --timeout` if discovery cannot reach local Sonos multicast.
- network/auth endpoint failures when IP is unreachable.
- bad IP formatting causes host resolution errors (e.g. `lookup 192.168.178.068: no such host`).
- invalid required arguments trigger usage errors with expected arg counts.
- Spotify Web API auth errors for `search spotify` when credentials are missing.
- queue operations fail if no active queue or invalid index is supplied.
- `No active source`-style playback errors happen if the selected target lacks the command context.
