## Smart home setup (huego / Philips Hue)

## Known resources

### Rooms
- `Mein Zimmer` — `82fafc26-083d-42e9-bfc5-0f481599b7a3`

### Zones
- `Decke` — `a494cafa-206b-4a90-8950-c9d15dc62e4a`
- `Ikea Leuchte` — `e9dcbac1-d3e6-4d09-a96b-0c74fbd211e6`

### Common lights
- `Schreibtisch-Licht` — `ab859e4a-eb52-4984-90bb-9931386d9ef8`
- `Deckenlampe` — `7230981a-c12f-41e0-bf45-5d13e1c91900`
- `Bettlicht` — `a5cc4288-5eb5-401a-9291-5aff9c57501d`
- `Hue color candle 1` — `dd47a116-5ade-43a9-95cb-48a66f8ef86c`
- `Hue color candle 2` — `6ec2171b-9052-4aef-990c-5b5063aefcc4`
- `Hue color candle 3` — `9ab6afa0-0abc-4c9f-963a-8f1f01576471`
- `Kleiderschranklicht` — `0d3bcdc8-783d-44fc-9bf5-49db5edf51ea`

### Note
Use names or IDs in commands; quote names with spaces.

## Speakers (sonos / Sonos)

- `Sonos Era 100` — `192.168.178.68` — `RINCON_804AF293A7EA01400`

### Note
`sonos discover` and `--name` never work from the sandbox. The container hangs
off Docker Desktop's NAT network (`192.168.65.0/24`), so an SSDP multicast has
no route to the LAN the speaker sits on. Unicast to the speaker's IP does get
routed, so always target it directly with `--ip 192.168.178.68`.
