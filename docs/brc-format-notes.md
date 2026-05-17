# CarScanner `.brc` format — reverse engineering notes

> Working notes from analyzing a single `.brc` export paired with its `.csv`
> twin (same trip). Not an official spec — CarScanner's format is proprietary
> and undocumented. Treat as best-effort; verify on new samples before relying
> on any field.

## Why these notes exist

CarScanner can export the same trip as `.csv` (verbose text) or `.brc`
(binary). The BRC is **~4.3× smaller** (3.4 MB vs 14.5 MB for the analyzed
trip). If we ever need to ingest CarScanner data and storage matters, we'd
want to parse BRC directly instead of CSV. The format is *partially*
decodable; this document records what's solid, what's plausible, and what's
still unknown.

## Source files used

- `90b17447-20260517_014721.csv` (14,519,239 B, 138,234 rows, 277 PIDs)
- `3ef57631-20260517_014721.brc` (3,404,822 B)
- Both exported from the same trip starting at `01:47:21` on 2026-05-17,
  vehicle: Peugeot 1.5 BlueHDI ECU MD1CS003, adapter: BTLE IOS-Vlink.

## File header (offsets 0x00..~0x76)

| Offset | Type | Content | Notes |
|---|---|---|---|
| 0x00 | u8 | length = 16 | always 0x10 |
| 0x01..0x10 | ASCII | `CARSCANNERRECORD` | magic |
| 0x11..0x14 | u32 LE | version = 2 | format version |
| 0x15 | u8+string | device id (length-prefixed) | e.g. `VXKUBYHTKM4329850` |
| ...   | u8+string | car name | e.g. `La mia auto` |
| ...   | u8+string | car model | e.g. `Peugeot 1.5 BlueHDI ECU MD1CS003` |
| ...   | u8+string | adapter | e.g. `BTLE IOS-Vlink` |
| 0x63  | u8 | length byte = 0x18 (24) | **but see caveat below** |
| 0x64..0x76 | 19 bytes | unknown | maybe Unix timestamp + flags; doesn't parse cleanly as doubles |
| 0x77..0x7e | double LE | **trip start latitude** | matches CSV first lat exactly |
| 0x7f..0x86 | double LE | **trip start longitude** | matches CSV first lon exactly |
| 0x87..0x8a | u32 LE | `13984144` (= 0x00D56190) | recurring "PID separator marker" — see below |
| 0x8b..0x8e | u32 LE | first PID code | here `241` = Velocità (GPS) |
| 0x8f.. | length-prefixed string | first PID name | start of PID stream |

### Caveat about the 24-byte "unknown block"
The length byte at 0x63 says 24, but the GPS lat at 0x77 starts INSIDE that
range and extends past it. Either the byte means something else (e.g. a flag,
a count of items, not a skip length), or the 19 bytes at 0x64..0x76 are a
self-contained header followed by a fixed `[lat, lon, separator, code]`
preamble that the writer pads/aligns differently. Treat the 19 unknown bytes
as opaque on read — the GPS coords and the separator+code at 0x87 are what
matter to find the first PID.

## PID stream

Each PID appears as a self-describing block:

```
[length u8][PID name UTF-8]   ← first copy (Italian by default)
[length u8][PID name UTF-8]   ← second copy (identical for our sample — could be
                                  English in other locales / dual-language exports)
[type u32 LE]                 ← CarScanner-internal "PID type" (NOT a count, NOT the OBD PID)
[record_0]
[record_1]
…
[record_{N-1}]
[separator u32 LE = 13984144]
[next_PID_code u32 LE]        ← code of the next PID name pair
```

The `[separator + next_code]` 8 bytes belong logically to the current PID block
but are also "the prefix" of the next one. The very last PID in the file uses
a different separator (see below).

### Records — two layouts observed

**Layout A — no GPS extras (24 bytes):**

| Offset | Type | Field |
|---|---|---|
| +0 | u32 LE | `ts` — raw, divide by 3000 to get seconds since midnight UTC of the file day |
| +4 | double LE | `first_sample_time` — seconds since session start when this PID was first sampled (CONSTANT per PID block) |
| +12 | u32 LE | `pid_code` — same value as `next_PID_code` from the previous separator. CarScanner-internal PID id |
| +16 | double LE | `value` — the sensor reading in display units (e.g. km/h, °C, kPa) |

**Layout B — with GPS extras (52 bytes):**

| Offset | Type | Field |
|---|---|---|
| +0..+23 | — | same 24 bytes as Layout A |
| +24 | u32 LE | unknown (some kind of GPS event reference; doesn't parse cleanly as `/3000` seconds) |
| +28 | double LE | unknown — possibly GPS speed at this sample (values like 7.84, 8.99 km/h fit) |
| +36 | double LE | **GPS latitude at this sample** |
| +44 | double LE | **GPS longitude at this sample** |

Which layout each record uses is **not yet trivially determined from the type
field**. Observed mapping for our sample:
- `Velocità (GPS)` type=1, 1 record, **layout A**
- `Altitudine (GPS)` type=20, 2 records, **layout B** (lat/lon match CSV ±)
- `Velocità media (GPS)` type=1, ~? records, **mixed** (first 3 look like A, then alignment drifts)
- `Giri motore x1000` type=6, 1 record, **layout A**
- `Giri motore` type=6, **multiple records, structure unclear** (block 191 B; 187 is prime, no clean fixed-size split)

Until we figure out the layout selector, the safest parser strategy is:
1. parse the FIRST record always as layout A (first reading is always present);
2. for subsequent records, attempt both A and B and pick whichever leaves the
   block ending exactly on the `[13984144, next_code]` separator.

## The "main data" block

The largest PID block ("Tasso di carburante del veicolo", 2.6 MB out of 3.4 MB)
is special. It does NOT just hold fuel-rate readings; it acts as a CONTAINER
for high-frequency time-series data of MANY OBD PIDs. Internally:

- It opens with a long run of **24-byte records** (Layout A), 222 of them in
  our sample, all sharing the same `ts = 6450.117 s`, with `mystery_d`
  increasing slowly from 39.9756 to 41.1453 (semantics unclear — may be a GPS
  km counter or a sub-sample index).
- The `pid_code` values inside this initial batch belong to PIDs that don't
  have their own top-level block: 660, 661, 721, 722, 723, 724, 725, 733,
  737, 741, 742, 743, 905, 906, 907, 908, 909. We don't know their meaning.
- After that initial batch, the block contains EMBEDDED PID name pairs
  (e.g. `Consumo istantaneo di carburante calcolato`) followed by their own
  data, recursively using the same block layout. So the file structure is
  actually a flat list of PID blocks with one "outer wrapper" block hosting
  the high-frequency PIDs nested inside.

> Practical consequence: a parser must keep scanning for `[13984144, code,
> length, name, length, name]` patterns inside the body, not assume one flat
> list at the top level.

## Separator constants

| Constant | Decimal | Where it appears |
|---|---|---|
| `0x00D56190` | 13984144 | separator before 42 of 46 top-level PIDs (mainstream Italian-named PIDs) |
| `0x5B2D17AC` | 1529217260 | separator before the last 4 PIDs (English-named "Calculated fuel injection amount", "Status of pre-post-heating relay", "EGR Low Limit Electronic Loading", "Proportional clutch pedal sensor") |

Both have a paired `u32` immediately after them: the next PID's code. The
second constant likely marks "extended/ECU-specific" PIDs that come from a
different OBD mode (Mode 22 instead of Mode 01), but this is unconfirmed.

## Time encoding

- `ts` field (`u32 LE / 3000`) = seconds since the day's midnight (UTC of the
  file timestamp).
- `mystery_d` / `first_sample_time` (`double LE`) = seconds since session
  start, where session start ≈ file timestamp + ~0.96 s. Verified against CSV
  for two PIDs:
  - `Temperatura d'aria ambiente`: expected 6476.5453s, CSV 6477.5067s, diff 0.96 s
  - `Sovralimentazione calcolata`: expected 6473.9021s, CSV 6474.8634s, diff 0.96 s

The 0.96 s offset is consistent across PIDs, so the session reference is a
single fixed value — likely the moment the OBD adapter signaled "connected".

## PID code → human name mapping

Built dynamically from the file itself by walking the PID stream. No need to
hardcode anything. Observed in our sample (top-level, sorted by appearance):

| code | name | type |
|---|---|---|
| 241 | Velocità (GPS) | 1 |
| 816 | Altitudine (GPS) | 20 |
| 543 | Velocità media (GPS) | 1 |
| 237 | Sovralimentazione calcolata | 48 |
| 900 | Giri motore x1000 | 6 |
| 12  | Giri motore | 6 |
| 807 | Power from MAF | 45 |
| 41  | Distanza percorsa con spia "avaria motore" accesa | 3 |
| 61  | Errore EGR | 14 |
| 233 | Velocità media | 1 |
| 235 | Distanza percorsa: | 3 |
| 236 | Accelerazione del veicolo | 43 |
| 94  | Temperatura d'aria ambiente | 15 |
| ... | (33 more) | ... |

The `type` field correlates loosely with units / sensor category but is NOT
the OBD PID number and NOT a record count.

## What we DON'T know (open questions)

1. **Layout selector**: which records in a block are Layout A (24 B) vs Layout
   B (52 B). Empirically we can detect it by alignment, but a deterministic
   rule would be cleaner. Hypothesis: tied to whether the PID is GPS-coupled
   in CarScanner's settings.
2. **The 19 unknown header bytes at 0x64..0x76**: probably contains a
   wall-clock timestamp (one of the 4-byte slices is ~1.5e9, consistent with
   2018-12 Unix seconds), but we haven't pinned it down.
3. **`mystery_d` in the big-block initial batch (39.97..41.14)**: doesn't fit
   the "session-seconds" interpretation (would mean 33-second spread before
   the first per-PID reading at 32.9s, which contradicts the ts of 6450.117s).
   Possibly a separate counter (GPS odometer? batch index?).
4. **Layout B field +24 (4 bytes)** and **field +28 (8-byte double)**: their
   exact semantics. The lat/lon at +36 / +44 are confirmed; the other two are
   only guessed.
5. **What determines the order of records within a block**: in `Velocità
   media (GPS)` the first three records reference different `pid_code`s (543,
   241, 816), suggesting cross-PID batching by GPS event rather than by PID.
6. **The 17 numeric pid_codes in the big-block init batch** (660, 661, 721-
   725, 733, 737, 741-743, 905-909): not declared anywhere in the file with a
   human name, so we can't map them without a CarScanner-side reference.
7. **Whether the format is stable across CarScanner app versions**. This is
   a `version=2` file. v1 likely exists and v3+ may break things silently.

## Implications for using BRC in production

**Pros:** 4.3× size reduction; faster to parse than CSV; self-describing PID
names mean no hardcoded mapping for the 46 top-level PIDs.

**Cons / risks:**
- Layouts B vs A detection is fragile.
- The huge embedded-PID block needs recursive scanning; one wrong assumption
  cascades.
- 17 numeric PIDs in the init batch have no name in the file → silent data
  loss unless we ship a hand-maintained code→name table.
- Single-sample reverse engineering: any branch the app didn't exercise in
  this file (different car, different sensors, dual-language export, v1 file,
  v3 file…) could break us.
- Bug-fix turnaround on a closed format means waiting for users to send broken
  files.

**Pragmatic recommendation:** keep CSV as the primary input path. If BRC
support becomes a must (e.g. mobile bandwidth), implement a parser that
extracts ONLY what we trust:
1. Header metadata (device, car, adapter, trip start lat/lon, trip start
   timestamp).
2. Top-level PID first-readings (one value per PID via the always-present
   first-record-as-layout-A trick).
Defer the time-series records (Layouts A subsequent / Layout B / nested
embedded PIDs) until we have a second sample to cross-check.

## Quick reference — minimal viable BRC reader

```python
import struct

def read_pstr(buf, pos):
    n = buf[pos]
    return buf[pos+1:pos+1+n].decode('utf-8'), pos+1+n

def parse_header(buf):
    pos = 0
    assert buf[pos] == 0x10 and buf[pos+1:pos+17] == b'CARSCANNERRECORD'
    pos = 17
    version = struct.unpack_from('<I', buf, pos)[0]; pos += 4
    device, pos = read_pstr(buf, pos)
    car,    pos = read_pstr(buf, pos)
    model,  pos = read_pstr(buf, pos)
    adapter, pos = read_pstr(buf, pos)
    # Skip the 19 opaque bytes then read trip start GPS + separator + first code.
    # Anchor on the GPS coordinates instead of trusting the byte at 0x63.
    pos += 1 + 19  # length byte + 19 unknown bytes
    lat = struct.unpack_from('<d', buf, pos)[0]; pos += 8
    lon = struct.unpack_from('<d', buf, pos)[0]; pos += 8
    sep = struct.unpack_from('<I', buf, pos)[0]; pos += 4  # expect 13984144
    first_code = struct.unpack_from('<I', buf, pos)[0]; pos += 4
    return dict(version=version, device=device, car=car, model=model,
                adapter=adapter, lat=lat, lon=lon, first_code=first_code), pos

def iter_pids(buf, pos):
    """Yield (code, name, type, first_reading_value) for each top-level PID."""
    while pos < len(buf) - 16:
        name_a, p1 = read_pstr(buf, pos)
        if p1 >= len(buf): break
        name_b, p2 = read_pstr(buf, p1)
        if name_a != name_b: break  # not a PID name pair
        type_v = struct.unpack_from('<I', buf, p2)[0]
        ts_raw = struct.unpack_from('<I', buf, p2+4)[0]
        first_sample_time = struct.unpack_from('<d', buf, p2+8)[0]
        code = struct.unpack_from('<I', buf, p2+16)[0]
        value = struct.unpack_from('<d', buf, p2+20)[0]
        yield code, name_a, type_v, value, ts_raw/3000, first_sample_time
        # Scan forward to the next separator (13984144) followed by a
        # plausible next_code. This is heuristic; refine when we have more data.
        sep_pos = buf.find(b'\x90\x61\xd5\x00', p2 + 28)
        if sep_pos < 0: break
        pos = sep_pos + 8  # skip [separator, next_code]
```
