---
name: spoti
description: Control Spotify playback, playback state, and your Spotify library via the official Spotify Web API.
metadata:
  status: ready
  cli_binary: spoti
---

# spoti CLI

A Spotify Web API CLI for playback control, searching, and library/playlist management. You need an active Spotify login (`spoti auth login`) before playback and user-data commands work.

## Namespaces

| Group | Controls | Notes |
| ----- | -------- | ----- |
| `auth` | Spotify authentication and app credentials | Required once per machine/session |
| `device` | Playback targets | List devices and transfer playback |
| `status` | Current playback state | Read-only state view |
| `play`, `pause`, `next`, `prev`, `seek`, `repeat`, `shuffle`, `volume` | Playback actions | Target with `--device <device-id>` when needed |
| `queue` | Queue management | Show queue and add tracks/episodes |
| `search` | Catalog lookup | Supports tracks/albums/artists/playlists/shows/episodes |
| `info` | Fetch by ID | Supports track/album/artist/playlist/show/episode |
| `library` | Saved tracks/albums/shows/episodes | Save/remove/list library items |
| `playlist` | Playlist CRUD and track edits | Add/remove/replace/list tracks |
| `user` | Listening profile | Profile, recent plays, top artists/tracks |

## Discovery

Known IDs and names for this workspace are in `tools.md`. Use them if present; otherwise discover:

```bash
spoti auth status
spoti device list
spoti status
spoti playlist list
```

## Common operations

```bash
spoti auth status
spoti auth login
spoti auth setup --client-id <client-id> [--client-secret <client-secret>] [--redirect-uri <uri>]
spoti auth logout

spoti device list
spoti device transfer <device-id> [--no-play]

spoti status
spoti play [uri] [--device <device-id>] [--type track|album|artist|playlist|show|episode]
spoti pause [--device <device-id>]
spoti next [--device <device-id>]
spoti prev [--device <device-id>]
spoti seek <ms> [--device <device-id>]
spoti repeat <track|context|off> [--device <device-id>]
spoti shuffle <on|off> [--device <device-id>]
spoti volume <0-100> [--device <device-id>]

spoti search <track|album|artist|playlist|show|episode> <query> [--limit 1-50] [--offset <n>]
spoti info <track|album|artist|playlist|show|episode> <id>

spoti queue show [--limit 1-50]
spoti queue add <uri> [--device <device-id>]

spoti library list <tracks|albums|shows|episodes> [--limit 1-50] [--offset <n>]
spoti library save <tracks|albums> <id>...
spoti library remove <tracks|albums> <id>...

spoti playlist list [--limit 1-50] [--offset <n>]
spoti playlist create <name> [--description <text>] [--public]
spoti playlist tracks <playlist-id> [--limit 1-50] [--offset <n>]
spoti playlist add <playlist-id> <uri>...
spoti playlist remove <playlist-id> <uri>...
spoti playlist replace <playlist-id> <uri>...
spoti playlist delete <playlist-id> [--yes]

spoti user me
spoti user history [--limit 1-50]
spoti user top-artists [--limit 1-50] [--offset <n>] [--time-range short_term|medium_term|long_term]
spoti user top-tracks [--limit 1-50] [--offset <n>] [--time-range short_term|medium_term|long_term]
```

## Exceptions

- `<device-id>` is required for some playback commands when Spotify cannot infer active device; discover IDs via `spoti device list`.
- `spoti play` can be run with no URI to resume current playback.
- `spoti info` and `spoti search` IDs/queries may contain shell-sensitive characters; quote `<query>` if needed.
- `<id>` values are IDs in Spotify URI format or plain IDs depending on endpoint.
- `<0-100>` for `volume` must be an integer; non-numeric or out-of-range values fail.
- Search and listing commands support pagination with `--limit` (`1-50`) and `--offset`.
- Playlist mutation commands that alter ownership state (`playlist delete`) require `--yes` for confirmable cleanup actions.

## Verification

```bash
spoti status
spoti device list
spoti queue show
spoti playlist list
spoti playlist tracks <playlist-id>
```

## Failure behavior

`spoti` returns non-zero exit codes on invalid arguments and auth/network/API failures. Examples: `spoti volume loud` fails with `must be an integer from 0 to 100`, and `--help` style usage errors occur when required arguments are missing. Common failures are:

- not logged in (`spoti auth status` shows unauthenticated), fixed with `spoti auth login`
- wrong or missing required IDs/arguments
- insufficient permission scopes for protected operations
- temporary API/network failures from Spotify
- no active playback target for device-specific commands
