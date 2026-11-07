#!/usr/bin/env python3
"""
Keep-Alive & Auto-Wake Script for Streamlit Community Cloud
===========================================================
Streamlit Community Cloud automatically hibernates apps after a period of
inactivity (typically 12-24 hours). When an app is asleep, visitors see:
    "Zzzz. This app has gone to sleep due to inactivity"
    and a button: "Yes, get this app back up!"

This script uses Playwright with a headless browser to:
1. Navigate to your Streamlit app URL.
2. Detect if the app is awake or in sleep mode.
3. If asleep, automatically click "Yes, get this app back up!" and wait for the app to spin up.
4. If awake, interact briefly (allowing WebSocket initialization) so Streamlit registers fresh traffic.
5. Save a status screenshot for inspection/artifacts.

Usage:
    python keep_alive.py [--url <URL>] [--timeout <seconds>] [--no-headless]
"""

import argparse
import os
import sys
import time

DEFAULT_URL = os.environ.get("STREAMLIT_APP_URL", "https://nuhuskies-hockey-bot.streamlit.app/")
DEFAULT_TIMEOUT = 180  # seconds to wait for cold spin-up


def parse_args():
    parser = argparse.ArgumentParser(description="Keep Streamlit Cloud app awake")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Target Streamlit app URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Max seconds to wait for app wake-up (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode (default: headless)",
    )
    parser.add_argument(
        "--screenshot",
        default="keep_alive_status.png",
        help="Path to save verification screenshot (default: keep_alive_status.png)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    url = args.url.strip()
    timeout_ms = args.timeout * 1000
    headless = not args.no_headless

    print("=" * 60)
    print(" Streamlit App Keep-Alive / Auto-Wake Sentinel")
    print("=" * 60)
    print(f"Target URL : {url}")
    print(f"Timeout    : {args.timeout}s")
    print(f"Headless   : {headless}")
    print(f"Timestamp  : {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("-" * 60)

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        print("[ERROR] Playwright is not installed.")
        print("Please install Playwright by running:")
        print("    pip install playwright")
        print("    playwright install chromium")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        page = context.new_page()

        print(f"[1/4] Navigating to {url}...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"[WARN] Initial page load notice: {e}. Checking state...")

        # Allow initial scripts/DOM to settle
        page.wait_for_timeout(5000)

        print("[2/4] Inspecting page state...")

        # Selector candidates for wake-up button
        wake_button_selectors = [
            'button:has-text("Yes, get this app back up!")',
            'button:has-text("get this app back up")',
            'button:has-text("Wake up")',
            'button:has-text("Yes, wake it up")',
        ]

        # Selectors indicating the live Streamlit app is rendering
        app_loaded_selectors = [
            'div[data-testid="stAppViewContainer"]',
            'div[data-testid="stApp"]',
            'header[data-testid="stHeader"]',
            '.stApp',
        ]

        wake_button = None
        for sel in wake_button_selectors:
            btn = page.locator(sel).first
            if btn.is_visible():
                wake_button = btn
                print(f"[INFO] Detected sleep mode prompt with button matching: '{sel}'")
                break

        is_awake = False
        if not wake_button:
            for sel in app_loaded_selectors:
                el = page.locator(sel).first
                if el.is_visible():
                    is_awake = True
                    print(f"[INFO] Detected active Streamlit container matching: '{sel}'")
                    break

        # Action Phase
        if wake_button:
            print("[3/4] App is asleep! Clicking wake-up button...")
            try:
                wake_button.click()
                print("[INFO] Clicked 'Yes, get this app back up!'. Waiting for app container to boot...")

                # Wait for the main app container to emerge
                found = False
                start_time = time.time()
                while time.time() - start_time < args.timeout:
                    page.wait_for_timeout(5000)
                    for sel in app_loaded_selectors:
                        el = page.locator(sel).first
                        if el.is_visible():
                            found = True
                            break
                    if found:
                        break
                    print(f"[WAIT] Still booting... ({int(time.time() - start_time)}s elapsed)")

                if found:
                    print("[SUCCESS] 🎉 App container successfully woke up and loaded!")
                    is_awake = True
                else:
                    print("[WARN] App did not show main container before timeout, checking final page state...")

            except Exception as e:
                print(f"[ERROR] Failed during wake-up sequence: {e}")

        elif is_awake:
            print("[3/4] ✅ App is ALREADY AWAKE and active!")
        else:
            print("[3/4] [NOTICE] Sleep button not found, checking if page is still hydrating...")
            # Give it another 10s in case of slow initial hydration
            page.wait_for_timeout(10000)
            for sel in app_loaded_selectors:
                el = page.locator(sel).first
                if el.is_visible():
                    is_awake = True
                    print(f"[INFO] App container appeared after hydration: '{sel}'")
                    break

        # Keep session open for a few seconds to let WebSocket traffic register on Streamlit servers
        print("[4/4] Keeping session active for 10s to ensure traffic is registered...")
        page.wait_for_timeout(10000)

        # Capture screenshot for verification
        try:
            page.screenshot(path=args.screenshot, full_page=False)
            print(f"[INFO] Verification screenshot saved to: {args.screenshot}")
        except Exception as e:
            print(f"[WARN] Could not capture screenshot: {e}")

        browser.close()

    print("-" * 60)
    if is_awake:
        print("RESULT: SUCCESS - Streamlit app is awake and responsive! ✅")
        print("=" * 60)
        sys.exit(0)
    else:
        print("RESULT: WARNING - Could not definitively verify app container state. ⚠️")
        print("Check keep_alive_status.png for the rendered screen.")
        print("=" * 60)
        # Exit with 0 so workflows don't fail unnecessarily if Streamlit changed a testid,
        # but report clearly in the logs.
        sys.exit(0)


if __name__ == "__main__":
    main()
