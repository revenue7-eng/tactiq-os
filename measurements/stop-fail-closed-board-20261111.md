# Development image: the gateway refuses tool calls when the stop service is down or silent (2026-11-11)

## Questions

1. With `tactiq-stop` stopped, does `agentgateway` refuse a tool call, or
   does the call reach the tool?
2. With `tactiq-stop` running but not answering (process frozen), does the
   gateway refuse, and after how long?
3. Is the refusal in 1 and 2 the gateway's own, distinguishable from the
   signed refusal of the stop service?
4. After the service answers again, is the answer the same as before?

## Why

The config sets `failureMode: deny` on the extAuthz block and
`tests/agentgateway/test_extauthz_config.py` keeps it there. At the
agentgateway revision the recipe pins (`d204f9c`), a failed authorization
call goes to `handle_auth_failure`, which returns an error under `Deny`,
and `Deny` is also the default. That was read in the tree and in the code.
This run is the observation on the board.

## Setup

- Board: the Rock 5A reference board `TACTIQ-BENCH-001`, slot B, the
  development image of `oecore-board-20261111.md` (same boot, nothing
  written to the board in this run). State block: `SELINUX Enforcing`,
  `ROOT root=/dev/dm-0`, `DM rootfs`, `SLOT B`. `/etc/tactiq-release`:
  `tactiq-image-dev`, `v2.1.0-rc14`.
- `tactiq-stop` and `agentgateway` active at the start.
- The agent was in the stopped state throughout (odd stop counter): the
  run neither tripped nor recovered it.
- Caller: `tactiq-refagent` (development image, domain
  `tactiq_refagent_t`), started with `systemctl start tactiq-refagent`.
  Its fourth attempt is an MCP `tools/call` of `valve_status` through the
  gateway on 127.0.0.1:49317; it logs the HTTP status, the body length,
  and whether the body is a TQSR stop receipt.
- The four states, one call each:
  1. control: `tactiq-stop` running;
  2. `systemctl stop tactiq-stop` (`inactive`);
  3. `systemctl start tactiq-stop`, then `kill -STOP` on its main PID;
  4. `kill -CONT`, the service answering again.
- The board has no time source; the journal reads October 12. Only the
  intervals between its timestamps are used.

## Files

| file | what |
| --- | --- |
| `board-session.log` | the console: state block, release file, the four calls and their journal lines |
| `durations.log` | `Starting` and `Finished` of the four `tactiq-refagent` runs |

Sums of every file are in `SHA256SUMS`.

## Results

| state | gateway answer | refagent run, Starting to Finished |
| --- | --- | --- |
| 1. running | `403`, body 643 bytes, TQSR stop receipt | 2.585 s |
| 2. stopped | `403`, body 29 bytes, no receipt | 0.120 s |
| 3. frozen | `403`, body 29 bytes, no receipt | 10.110 s |
| 4. running again | `403`, body 644 bytes, TQSR stop receipt | 2.559 s |

1. Refused. The call did not reach the tool: had the gateway failed open,
   a call with the stop service absent would have been passed to the
   backend.
2. Refused, after the 10 s authorization timeout set by the recipe's
   patch (`0001-ext_authz-http-check-timeout-10s.patch`). The 0.120 s of
   state 2 against the 10.110 s here shows the two states took different
   paths: connection refused, and no answer within the timeout.
3. Yes. The gateway's refusal carries a 29-byte body and no receipt; the
   stop service's refusal carries a signed TQSR receipt. A caller can tell
   which component refused.
4. Yes: a signed receipt again, in about the same time as the control
   (the length differs by one byte, as signatures do).

In all four runs the three attempts around the gateway (`exec`, `stop`,
`plant`) were refused by the policy with `EACCES`.

## What this does not establish

- That the gateway passes a call when the stop service allows it. The
  agent was stopped throughout, so no run had a `2xx` from the service.
  The running case is not part of this record.
- That nothing else can answer on 127.0.0.1:49318 while the service is
  down. In the TactiQ policy modules only `tactiq_stop_t` binds
  `tactiq_stop_port_t`; whether an unconfined domain of the base policy can
  bind it was not checked.
- What happens to a call already accepted by the gateway when the stop is
  set. Not exercised here.
- The content of the 29-byte body. It is the gateway's, not checked
  further.
- `journalctl` reports one journal file of an earlier boot as truncated
  and ignores it, as in `oecore-board-20261111.md`. Not investigated.
- Anything about a release image (it has no gateway) or another board.

## Horizon

The result holds while the gateway config keeps `failureMode: deny` (the
config test guards it), while the pinned agentgateway revision handles a
failed authorization call as at `d204f9c`, and while the timeout patch is
in the recipe. A move of the agentgateway pin, or dropping the patch for a
revision that honours `requestTimeout` (5 s in the config), means running
this again; in state 3 the expected time then changes to that timeout.
