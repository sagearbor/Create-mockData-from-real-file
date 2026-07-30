#!/usr/bin/env python3
"""
UI Testing Script for BYOD Synthetic Data Generator
Run with: python tests/scripts/test_ui.py
"""

import asyncio
import os
from datetime import datetime

import pytest

# Playwright is an optional dev dependency; skip the module rather than failing
# collection for everyone who has not installed it and its browsers.
async_playwright = pytest.importorskip(
    "playwright.async_api",
    reason="playwright not installed; run `pip install playwright && playwright install`",
).async_playwright

pytestmark = [pytest.mark.requires_server, pytest.mark.requires_playwright]

SCREENSHOTS_DIR = "tests/screenshots"
BASE_URL = "http://localhost:8201"

async def test_ui_components():
    """Test various UI components and take screenshots"""

    # Ensure screenshots directory exists
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({'width': 1920, 'height': 1080})

        print(f"Testing UI at {BASE_URL}")

        # Test 1: Initial page load
        await page.goto(BASE_URL)
        await page.wait_for_timeout(2000)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        await page.screenshot(path=f'{SCREENSHOTS_DIR}/ui_initial_{timestamp}.png')
        print("✓ Initial page loaded")

        # Test 2: Load demo data
        await page.select_option('#demoDataset', 'sales')
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f'{SCREENSHOTS_DIR}/ui_demo_loaded_{timestamp}.png')
        print("✓ Demo data loaded")

        # Test 3: Test tooltips
        tooltips = await page.query_selector_all('.info-tooltip-icon')
        for i, tooltip in enumerate(tooltips[:3]):  # Test first 3 tooltips
            try:
                await tooltip.hover()
                await page.wait_for_timeout(500)
                await page.screenshot(path=f'{SCREENSHOTS_DIR}/ui_tooltip_{i}_{timestamp}.png')
                print(f"✓ Tooltip {i} tested")
            except:
                print(f"✗ Tooltip {i} failed")

        # Test 4: Mobile view
        await page.set_viewport_size({'width': 375, 'height': 812})
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f'{SCREENSHOTS_DIR}/ui_mobile_{timestamp}.png')
        print("✓ Mobile view tested")

        await browser.close()
        print(f"\nAll screenshots saved to {SCREENSHOTS_DIR}")

if __name__ == "__main__":
    asyncio.run(test_ui_components())