"""The captures that reach into a poker client, kept apart from the rest of fpdb (#451).

Everything here *acquires* hands from a client rather than reading files a room
writes:

- ``swc_client``, ``swc_tap_build``, ``swc_windows_inject`` and the C sources
  beside them build the SwC tap and load it into the SwC client -- injected on
  Windows, preloaded at launch on macOS and Linux;
- ``swc_http_capture`` and ``swc_poker_console`` drive the SwC web client
  through a browser (Playwright, from the ``[capture]`` extra);
- ``coinpoker_pcap``, ``coinpoker_live_capture`` and ``GuiCoinPokerCapture``
  record the CoinPoker client's network packets.

fpdb imports nothing from here at module level. The core decodes what a capture
wrote -- ``swc_native_capture``, ``http_capture_*``, ``coinpoker_hand_builder``
-- and reaches into this package only from the action that starts a capture,
which says so when the package is missing. Each capture also stays off until
its user turned it on (:mod:`fpdb_3_legacy.live_capture_consent`).
"""
