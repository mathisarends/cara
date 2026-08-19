---
name: huego
description: Inspect and control Philips Hue lights, rooms, zones, and scenes via the local bridge.
metadata:
  status: ready
---

# huego CLI

A Philips Hue controller backed by the local CLIP v2 API. You need bridge discovery and registration (`huego setup`) to have credentials and a configured bridge before controlling anything.

## Namespaces

| Group   | Controls                        | Notes                                              |
| ------- | ------------------------------- | -------------------------------------------------- |
| `light` | Individual lights by ID or name | Also accepts room/zone targets for shared commands |
| `room`  | Rooms                           | Mirror operations from `light` for bulk control    |
| `zone`  | Zones                           | Mirror operations from `light` for bulk control    |
| `scene` | Scenes                          | List and activate pre-defined scenes               |
| `setup` | Bridge pairing                  | Interactive discovery and registration             |

## Discovery

Known IDs and names for this workspace are in `tools.md`. Use them if present; otherwise discover:

```bash
huego light list
huego room list
huego zone list
huego scene list
```

## Common operations

```bash
huego light list
huego room list
huego zone list
huego scene list

huego light on <target>
huego room on <target>
huego zone on <target>
huego light off <target>
huego room off <target>
huego zone off <target>

huego light toggle <target>
huego room toggle <target>
huego zone toggle <target>

huego light brightness <target> <percent>
huego room brightness <target> <percent>
huego zone brightness <target> <percent>

huego light color <target> <color>
huego room color <target> <color>
huego zone color <target> <color>

huego light temperature <target> <kelvin>
huego room temperature <target> <kelvin>
huego zone temperature <target> <kelvin>

huego light identify <target>
huego room identify <target>
huego zone identify <target>

huego scene activate <target>
```

Optional flags used for smooth transitions:

```bash
huego light on <target> --brightness <percent> --transition <seconds>
huego light off <target> --transition <seconds>
huego light brightness <target> <percent> --transition <seconds>
huego light color <target> <color> --brightness <percent> --transition <seconds>
huego light temperature <target> <kelvin> --brightness <percent> --transition <seconds>
huego scene activate <target> --brightness <percent> --transition <seconds> --dynamic
```

## Exceptions

`<target>` is required for all target operations and may be either a name or UUID-like ID; quote names with spaces, e.g. `"Mein Zimmer"`.
`<percent>` is a brightness float expected in the range `0` to `100`; `0` turns the target off.
`<color>` accepts a CSS-style name, `#rgb`, or `#rrggbb` value.
`<kelvin>` is a numeric color temperature in Kelvin.
`<seconds>` is a float used as fade duration.

Room/zone commands expose the same controls as light commands and support the same target and optional flag behavior.

## Verification

```bash
huego light list
huego room list
huego zone list
huego scene list
```

Use discovery output to verify that state changed as expected (`(on)` / `(off)` and scene activation state).

## Failure behavior

`huego` returns non-zero exit codes for argument/validation errors. Missing required args produces usage-style errors such as:

```bash
huego light brightness
# error: accepts 2 arg(s), received 0
```

Common failures are invalid targets, malformed colors/values, and unset bridge credentials until `huego setup` has been completed.
