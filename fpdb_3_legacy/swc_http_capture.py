#!/usr/bin/env python3
"""Playwright transport for SwC Poker HTTP/WebSocket capture."""

from __future__ import annotations

import logging
import os
import sys
import time

from fpdb_3_legacy.http_capture_archive import JsonHandArchive, JsonlRawCaptureArchive
from fpdb_3_legacy.http_capture_models import RawCaptureMessage
from fpdb_3_legacy.swc_http_adapter import (
    SwCHttpAdapter,
    describe_socketio_frame,
    extract_game_state_from_socketio,
    utc_now_iso,
)

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[ERROR] Playwright library is not installed.")
    print("[ERROR] Please install Playwright (pip install playwright && playwright install chromium).")
    sys.exit(1)


output_dir = os.path.expanduser("~/Documents/SwC Poker/Capture/")
raw_archive = JsonlRawCaptureArchive(output_dir)
hand_archive = JsonHandArchive(output_dir)
adapter = SwCHttpAdapter()
log = logging.getLogger(__name__)

print(f"[INFO] Capture artifacts will be saved in: {output_dir}")

captured_hands_count = 0
last_hand_id = None
page_ref = None


def update_ui_status_bar() -> None:
    if not page_ref:
        return
    try:
        status_text = f"🟢 FPDB CAPTURE ACTIVE | Hands: {captured_hands_count} | Last: {f'#{last_hand_id}' if last_hand_id else '--'}"
        page_ref.evaluate(
            f"""
            const bar = document.getElementById('fpdb-status-bar');
            if (bar) {{
                bar.innerHTML = '{status_text}';
                bar.style.borderColor = '#00ff00';
                bar.style.color = '#00ff00';
            }}
        """
        )
    except PlaywrightError:
        log.debug("Unable to update the SwC capture status bar", exc_info=True)


def save_finalized_hands(hands: list[dict]) -> None:
    global captured_hands_count
    for hand_data in hands:
        try:
            filepath = hand_archive.write_hand(hand_data)
            captured_hands_count += 1
            print(f"[SUCCESS] Hand #{hand_data['hand_id']} ({hand_data['game_type']}) saved to {filepath}")
        except (KeyError, OSError, TypeError, ValueError) as exc:
            print(f"[ERROR] Error saving hand #{hand_data.get('hand_id')}: {exc}")


def process_websocket_payload(payload: str, ws_url: str | None = None, direction: str = "received") -> None:
    global last_hand_id

    captured_at = utc_now_iso()
    frame_info = describe_socketio_frame(payload)
    game_state = extract_game_state_from_socketio(payload)

    raw_ref = raw_archive.append(
        RawCaptureMessage(
            site=adapter.site,
            transport="websocket",
            endpoint=ws_url,
            message_type=frame_info["message_type"],
            table_id=game_state.get("ti") if game_state else None,
            hand_id=game_state.get("gi") if game_state else None,
            captured_at=captured_at,
            payload=payload,
            direction=direction,
        )
    )
    if not game_state:
        return

    result = adapter.process_game_state(game_state, captured_at=captured_at, raw_ref=raw_ref)
    if result.hand_id:
        last_hand_id = result.hand_id
    save_finalized_hands(result.finalized_hands)
    update_ui_status_bar()


def run() -> None:
    global page_ref
    print("[INFO] Starting Playwright...")
    with sync_playwright() as p:
        try:
            print("[INFO] Launching Chromium browser...")
            browser = p.chromium.launch(headless=False)
        except PlaywrightError as e:
            err_str = str(e)
            if "Executable doesn't exist" in err_str or "playwright install" in err_str:
                print("[INFO] Chromium not found. Downloading Chromium automatically through Playwright...")
                import subprocess

                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                browser = p.chromium.launch(headless=False)
            else:
                raise

        page = browser.new_page()
        page_ref = page

        def inject_gui_status_bar() -> None:
            try:
                page.evaluate(
                    """
                    if (!document.getElementById('fpdb-status-bar')) {
                        const style = document.createElement('style');
                        style.innerHTML = `
                            #fpdb-status-bar {
                                position: fixed;
                                bottom: 12px;
                                left: 12px;
                                background: rgba(20, 20, 20, 0.95);
                                color: #ff9900;
                                padding: 8px 16px;
                                border-radius: 8px;
                                border: 2px solid #ff9900;
                                font-family: 'Courier New', Courier, monospace;
                                font-size: 13px;
                                font-weight: bold;
                                z-index: 2147483647;
                                pointer-events: none;
                                box-shadow: 0 4px 15px rgba(0,0,0,0.7);
                                letter-spacing: 0.5px;
                                transition: all 0.3s ease;
                            }
                        `;
                        document.head.appendChild(style);
                        const bar = document.createElement('div');
                        bar.id = 'fpdb-status-bar';
                        bar.innerHTML = '🟡 FPDB CAPTURE WAITING FOR GAME';
                        document.body.appendChild(bar);
                    }
                """
                )
            except PlaywrightError:
                log.debug("Unable to inject the SwC capture status bar", exc_info=True)

        page.on("domcontentloaded", lambda _: inject_gui_status_bar())

        def on_websocket(ws) -> None:
            print(f"[INFO] Connected to game server: {ws.url}")

            def on_received(payload) -> None:
                if isinstance(payload, str):
                    try:
                        inject_gui_status_bar()
                        process_websocket_payload(payload, ws.url, direction="received")
                    except Exception:  # noqa: BLE001 - callback boundary: log malformed/capture failures and keep listening.
                        log.exception("Failed to process an incoming SwC WebSocket frame")

            def on_sent(payload) -> None:
                if isinstance(payload, str):
                    try:
                        process_websocket_payload(payload, ws.url, direction="sent")
                    except Exception:  # noqa: BLE001 - callback boundary: log malformed/capture failures and keep listening.
                        log.exception("Failed to process an outgoing SwC WebSocket frame")

            ws.on("framereceived", on_received)
            ws.on("framesent", on_sent)

        page.on("websocket", on_websocket)
        page.goto("https://play.swcpoker.club")

        print("[INFO] === SwC HTTP Capture Active ===")
        while True:
            try:
                if page.is_closed():
                    break
                inject_gui_status_bar()
                update_ui_status_bar()
                time.sleep(1)
            except PlaywrightError:
                log.info("SwC browser page closed while capture was active", exc_info=True)
                break
        browser.close()


if __name__ == "__main__":
    run()
