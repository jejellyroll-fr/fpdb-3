# Live capture: off until you turn it on

fpdb imports the hand histories your rooms write. That is the recommended
source, and nothing about it touches a poker client: fpdb reads files the
client leaves on disk. Winamax's live HUD context works the same way, from the
client's own log (`winamax_live_log_reader.py`) and the accessibility tree the
operating system exposes (`winamax_ax_seats.py`).

A room that writes no hand histories leaves only the client itself to read the
hands from. Two captures do that, and they go further than reading files:

| Capture | What it does |
| --- | --- |
| **SwC client tap** (Seals with Clubs) | Loads a small library of fpdb's into the SwC Poker client: injected into the running client on Windows, preloaded with `DYLD_INSERT_LIBRARIES` / `LD_PRELOAD` when fpdb launches the client on macOS and Linux. It reads the table traffic after the client has decrypted it, and stays loaded until the client exits. See [swc-native-capture.md](swc-native-capture.md). |
| **CoinPoker packet capture** | Records the CoinPoker client's network packets with administrator rights (tcpdump, pkexec or a UAC prompt). It loads nothing into the client. CoinPoker support is switched off for now, so this one is not offered. |

Anti-cheat systems look for software that loads into a poker client or reads
its traffic. A room may treat that as a breach of its terms and restrict or
close the account, whatever fpdb does with the data. **Your room's terms
prevail**: read them before turning a capture on.

## Turning a capture on

Both captures are off on a fresh install. Starting Auto Import never loads
anything into a client until you turn the SwC tap on. It imports the SwC files
and says the capture is off.

Open **Tools ▸ Live capture…** and tick the capture. fpdb shows what it does,
the account risk and that the room's terms prevail, and turns it on only when
you choose **I understand, turn it on**. Untick it to turn it off again.
Starting the CoinPoker capture from its tab asks the same question.

The command-line capture (`python -m fpdb_3_legacy.capture.swc_client`) asks
on the terminal and turns the tap on only when you type `yes`. Run from
something that is not a terminal, it refuses rather than assuming a yes.
`--build` only compiles the tap and needs no answer.

## Where the capture code lives

Everything that reaches into a client is in its own package,
`fpdb_3_legacy/capture/`:

- the SwC tap: its C sources, the build, the Windows injector and the command
  above (`swc_client`);
- the SwC web capture (`swc_http_capture`, `swc_poker_console`);
- the CoinPoker packet capture and its tab.

fpdb's core never imports it when it starts. It decodes what a capture wrote
(`swc_native_capture`, `http_capture_*`), and reaches into the package only
from the action that starts a capture. An install without the package still
starts, imports hand histories and runs the HUD; starting a capture then says
it is not part of this install. A test (`tests/test_capture_isolation.py`)
keeps it that way.

The SwC web capture needs Playwright, which only the `capture` extra brings:

```sh
pip install -e '.[capture]'
playwright install chromium
```

## Where the answer is kept

In `live-capture-consent.json`, beside `HUD_config.xml`:

```json
{
  "accepted": {
    "swc_native": {"version": 1, "accepted_at": "2026-10-30T19:00:00+00:00"}
  }
}
```

Each capture has a version. When a capture changes what it loads or reads, its
version moves, and the old answer no longer counts: fpdb asks again. Deleting
the file turns every capture off.

## What fpdb never does

Whichever captures are on, fpdb shows opponents' history and your own results.
It never shows a recommended action and never acts in the client.
