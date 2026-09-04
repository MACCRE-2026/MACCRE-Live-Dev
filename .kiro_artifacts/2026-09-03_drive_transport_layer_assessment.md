# Assessing the Google Drive "Header Space" Transport Layer

**Written:** 2026-09-03
**Nature:** Technical assessment. Modifies no code.
**Question asked:** *"Verify if there really is 32 KB of header space for us to use as the
transport layer by writing to the header data instead of the file… somehow AG and I had come
to determine that this was very efficient and operates on existing service overhead without
needing any network protocol layer, though we could have just been 'yes, and'-ing each other,
so let's assess."*

**Short answer.** The **goal is sound and achievable.** The **mechanism as described does not
work**, and the 32 KB figure is wrong by roughly an order of magnitude for the only usable
version of it. The part that makes it attractive — *no network protocol layer* — is the part
that fails hardest: reaching that space requires the Drive API, which is a network protocol
layer. There is a cruder design that does work, needs no API, and is architecturally
consistent with what MACCRE already is.

Assessed with the operator's explicit invitation to conclude they had been "yes, and"-ing.
That was the right instinct to have.

---

## 1. "Header space" has three possible meanings, and they behave completely differently

The phrase is ambiguous, and the ambiguity is where the idea went wrong. Each reading is
assessed separately because the answer flips between them.

### Reading A — Drive API custom file properties (`properties` / `appProperties`)

This is almost certainly the intended one, and it is where a number like 32 KB could plausibly
have come from.

**Measured limits, from the current official documentation**
([Google, Add custom file properties](https://developers.google.com/workspace/drive/api/guides/properties)):

| Limit | Value |
|---|---|
| Custom properties per file, all sources | **100** |
| Public properties per file, all sources | **30** |
| Private properties per file, per application | **30** |
| **Bytes per property, key + value combined, UTF-8** | **124** |

*Content was rephrased for compliance with licensing restrictions.*

**So the arithmetic, which is the whole point:**

- One application via `appProperties`: 30 × 124 = **3,720 bytes ≈ 3.6 KiB**
- Plus public `properties`: another 30 × 124 = 3,720 → **7,440 bytes ≈ 7.3 KiB** total
- Absolute ceiling if every source is used: 100 × 124 = **12,400 bytes ≈ 12.1 KiB**

And that is *before* overhead. Keys consume the same 124-byte budget as values, so a 3-character
key leaves 121 bytes of value. If the payload is binary and needs base64, subtract another 33%.
Realistic usable payload for one app: **roughly 2.5–2.7 KiB.**

**Verdict on the number: 32 KB is not available. The usable figure is about a tenth of that.**

**And the fatal objection is architectural, not numerical.** `properties` and `appProperties`
are fields on the Drive API's `files` resource. Every documented way to read or write them is
an API call — `files.update` via `PATCH`, `files.get` with a `fields` parameter. The
documentation is explicit that private properties cannot even be *read* without an OAuth 2.0
access token, and that an API key will not do it.

**Therefore, to use this space you must:**

1. hold an OAuth 2.0 client credential on both devices,
2. perform a token exchange,
3. issue authenticated HTTPS requests.

That is a network protocol layer, an auth layer, and a Google dependency in the transport path.
The stated benefit — *operates on existing service overhead without needing any network
protocol layer* — is exactly what is not true. And once you are making API calls, **writing a
small file is simpler and has no size ceiling at all**, which makes the header approach
strictly worse than the obvious alternative.

**Marked as inference, not fact:** I could find no source describing custom-property access
through the mounted filesystem, and none stating outright that Drive for desktop ignores them.
The documentation describes the desktop client purely in terms of file content sync and
describes properties purely as API-resource fields, with no mechanism connecting the two. That
is strong one-sided evidence rather than a confirmed negative. **The settling test is one API
call:** set an `appProperty` on a file, then look for any trace of it in the mirrored folder.
Ten minutes, and it would convert this inference into a fact.

### Reading B — a *file format's* header (EXIF, XMP, ID3, container padding)

This one **does** sync, because it is file content. A JPEG's EXIF `APP1` segment is capped near
64 KB, which is another plausible origin for a remembered "32 KB", and XMP packets are
routinely padded to a few KB. So a payload genuinely can ride inside an image that Drive
mirrors normally, with no API and no credentials.

**But it buys nothing here.** If you can sync a JPEG carrying 32 KB in its EXIF, you can sync a
32 KB `.json`. The only reason to hide a payload inside a media header is to *disguise* it from
something inspecting the file — and on the operator's own Drive, with the operator on both
ends, there is nothing to disguise it from. It adds an encode/decode step, a dependency, a
silent truncation mode, and a new way to be wrong, in exchange for nothing.

### Reading C — filesystem metadata / NTFS Alternate Data Streams

**Does not survive.** ADS is an NTFS construct; it is not preserved by Drive upload and cannot
exist on Android at all.

This reading turned out to matter for an unrelated reason — see §4, which is the most valuable
thing this assessment produced and had nothing to do with the original question.

---

## 2. The design that does work

**A file as a mailbox, through the mirrored folder.** No API, no OAuth, no network code.

```
laptop  ->  <shared>/inbox/req_<uuid>.json      { prompt, model, params, created_at }
phone   ->  polls inbox/, claims, runs local model
phone   ->  <shared>/outbox/res_<uuid>.json     { text, tokens, cost, finished_at }
laptop  ->  polls outbox/, matches on uuid
```

**Why this is the right shape for MACCRE specifically:** the system already *is* a file-and-queue
architecture with a durable claim protocol. This is the same pattern with Drive as the courier
instead of SQLite, and it reuses reasoning the project has already paid for. No payload ceiling,
no encoding tricks, no credentials in the transport path.

**Honest costs, none of them fatal but all of them real:**

- **Latency is a courier, not a transport.** Drive sync is seconds to minutes and is not
  bounded. Fine for "run this on the phone and have an answer in a minute"; useless for
  anything interactive. The design should be *asynchronous by construction* rather than
  request/response with a timeout, because a timeout here would mostly measure Drive's mood.
- **No ordering or delivery guarantee.** Needs the same discipline the broker already has:
  claim before work, and a claim that is visible so a second reader does not duplicate it.
- **Conflict forks.** Simultaneous writes produce `res_x (1).json`. This is already register
  Chain B link 4 (*conflict-fork detection*), and it applies here verbatim — a silent fork is
  invisible until something goes missing.
- **Never put SQLite in the shared folder.** Doctrine 8, and the workspace is already carrying
  68 live `-wal` sidecars under an active sync client. A mailbox of plain files is safe
  precisely because each file is independently meaningful; a database is not.
- **Polling cost** on a phone is battery, and the register's Android entry already flags
  throttling as the binding constraint.

---

## 3. The sovereignty question, which is the operator's to answer

The contract states that **Sovereign Importer is the only location outside the MACCRE
datacenter that MACCRE can reach**, and that nothing crosses into MACCRE without its
provenance artifacts, pushed from the Importer.

A Drive-mediated laptop↔phone channel is a **second egress and ingress path that does not pass
through the Importer.** Both endpoints are the operator's own devices, which is the strongest
possible mitigation, and it may well be an acceptable exception — but it is an exception to the
contract's central clause, and the contract's own style is to name such things explicitly
rather than let them be silent. The gating of MACCRE behind the Importer is already recorded as
an *acknowledged* violation of principle; this would be the second, and it should be recorded
the same way rather than discovered later.

**It is also the shape of an SOP.** If this channel is built, the Sovereign Importer team
learns that MACCRE has a second path in and out — before it breaks their assumption that the
Importer is the only one. That is exactly what an SOP is for, and it costs one document.

---

## 4. What this assessment turned up that was not asked for

Chasing Reading C led into `maccre_core/utils/secret_auth.py`, and there is a finding there
worth more than the answer to the original question. It is recorded as its own register entry;
the summary is:

- The module's docstring advertises **"Air-Gap Steganographic Hardware Authentication… Uses
  NTFS Alternate Data Streams and Hardware tokens."**
- `is_topology_approved()` **unconditionally returns `True`.** The gate is disabled, by
  deliberate operator decision, and the function's own docstring says so — but the module
  docstring still describes the control as active, and `topology_engine.py`'s
  `PermissionError(f"DENIED: Topology … lacks Hardware Auth Stamp.")` is therefore unreachable.
- `secret_auth.py` does `from ctypes import wintypes` **at module scope**, which fails on
  non-Windows. `topology_engine._pull_from_csv` imports it **unguarded**. So the topology loader
  — on every execution path — **cannot run off Windows**, for the sake of a gate that returns
  `True`.

That last point is a **hard Android blocker of the same class as the DPAPI credential vault**,
and unlike the vault it is removable in about two lines, because nothing depends on the value.

---

## 5. Confidence

**Confirmed from official documentation, cited:** the four custom-property limits, and that
private properties require an OAuth access token rather than an API key.

**Confirmed by code read this session:** `is_topology_approved` returning `True`
unconditionally; `from ctypes import wintypes` at `secret_auth` module scope;
`topology_engine._pull_from_csv`'s unguarded import; `pattern_executor`'s guarded import and
its unconditional ADS write; `stamp_topology`'s USB-serial hardware check still being real.

**Inference, marked as such:** that Drive for desktop does not expose custom properties through
the mirrored folder. One API call settles it.

**Not determined:**
- The actual end-to-end latency of a Drive-mediated mailbox between these two specific devices.
  It should be measured before anything is designed around it, and it is a ten-minute test:
  write a file on the laptop, watch for it on the phone, record the spread over several tries.
- Whether the remembered "32 KB" came from the 100 × 124 ≈ 12 KiB property ceiling, from EXIF's
  ~64 KB `APP1` cap, or from somewhere else. It does not matter for the decision.
- Whether Android's Drive app exposes a mirrored *folder* at all, or only the streaming client.
  **This is the load-bearing unknown for the mailbox design** — the whole approach assumes the
  phone can see a synced directory in the filesystem. On Android that is not a given, and if it
  is not true the mailbox needs the API after all, at which point it and Reading A collapse into
  the same design and the API becomes unavoidable.
