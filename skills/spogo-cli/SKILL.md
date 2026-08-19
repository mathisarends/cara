---
name: spogo-cli
description: Control Spotify playback with the spogo CLI, including status, play and pause, track navigation, volume, shuffle, repeat, seeking, search, queues, devices, and playlists. Use whenever the user asks to inspect or control Spotify from the terminal.
---

# Spogo CLI

`spogo` 0.10.0 controls Spotify through stored web cookies. Authentication is configured when `spogo auth status --plain` reports valid cookie fields. Check state and target devices before a playback mutation:

```bash
spogo status --plain
spogo device list --plain
```

`status --plain` prints tab-separated playback state, progress, IDs and title; it can still identify a paused item. Device IDs and names are accepted by `--device`; quote names with spaces. Pass `--device <name-or-id>` to any playback command to target it. Devices must be available/active in Spotify; the list indicates availability in its final field.

## Commands

| Group | Purpose |
|---|---|
| `auth` | Inspect, import, paste, or clear browser-cookie authentication. |
| `search` | Find tracks, albums, artists, playlists, episodes, and shows. |
| `play`, `pause`, `next`, `prev`, `seek`, `volume` | Playback control. |
| `shuffle`, `repeat`, `status` | Playback state. |
| `queue` | Add, view, or clear the queue. |
| `device` | List devices and select a default active device. |
| `library`, `playlist`, `user` | Saved music, playlists, and listening data. |

## Playback

```bash
# Resume current playback
spogo play

# Play an item: Spotify URI/URL is unambiguous; a raw ID needs --type
spogo play 'spotify:track:<id>'
spogo play 'https://open.spotify.com/playlist/<id>'
spogo play <id> --type track

spogo pause
spogo next
spogo prev
spogo seek 1:30             # also accepts milliseconds
spogo volume 35             # range: 0–100
spogo shuffle on            # on|off
spogo repeat context        # off|track|context
```

Target a device directly when appropriate:

```bash
spogo play 'spotify:track:<id>' --device 'Sonos Era 100'
spogo volume 25 --device <device-id>
```

Verify a playback change with `spogo status --plain`. Do not assume a device name from local audio-output aliases maps to Spotify; inspect `device list` first.

## Search and queues

```bash
spogo search track '<query>' --limit 5 --plain
spogo search album '<query>' --limit 5 --plain
spogo search artist '<query>' --limit 5 --plain
spogo search playlist '<query>' --limit 5 --plain

spogo queue show
spogo queue add 'spotify:track:<id>'
spogo queue clear
```

Search output with `--plain` is tab-separated and starts with resource type and ID; tracks then include title, artist, album, and URI. Queue additions and clearing change playback state; check `queue show` afterward.

## Devices

```bash
spogo device list
spogo device set <device-name-or-id>
```

`device set` establishes the CLI's active target. For a one-off action, prefer `--device` so the saved default is not changed.

## Library and playlists

```bash
spogo library tracks list --limit 50
spogo library tracks add <id-or-uri> ...
spogo library tracks remove <id-or-uri> ...
spogo library albums list --limit 50
spogo library artists list --limit 50

spogo playlist create '<name>'
spogo playlist create '<name>' --public
spogo playlist create '<name>' --collab
spogo playlist tracks <playlist-id-or-uri>
spogo playlist add <playlist-id-or-uri> <track-id-or-uri> ...
spogo playlist remove <playlist-id-or-uri> <track-id-or-uri> ...
```

Playlist and library writes are consequential. List or inspect first, then verify with the corresponding list/tracks command.

## Output and failures

- `--plain` is useful for script-friendly tab-separated output; `--json` provides structured output.
- Global `--timeout` defaults to ten seconds. `--market`, `--language`, `--profile`, and `--engine` (`auto`, `web`, `connect`, `applescript`) alter request behavior when needed.
- The CLI returns a nonzero error for bad arguments, unavailable playback/device state, expired authentication, or unsupported operations. Inspect `spogo auth status`, `spogo device list`, and `spogo status` before retrying rather than guessing.
