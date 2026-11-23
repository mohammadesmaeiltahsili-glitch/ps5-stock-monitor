#!/usr/bin/env python3
"""
PS5 Stock & Price Monitoring Bot
PlayStation Direct Germany (de-de)

Monitors PlayStation Direct Germany for brand-new PS5 Disc Edition consoles
priced <= 650.00 EUR and notifies via Telegram.
"""

import html
import logging
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional

import requests
from playwright.sync_api import sync_playwright

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("PS5Monitor")

# ---------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------
TARGET_MAX_PRICE = 650.0  # Max price in EUR

TARGET_URLS = [
    "https://www.playstation.com/api/pdp-redirect/?locale=de-de&id=PSD001-PSDE01929_59-PS5CONSOLEHB2OYE",
    "https://www.playstation.com/api/pdp-redirect/?locale=de-de&id=PSD001-PSDE00233_59-PS5GRADEDCLIZSLE",
    "https://www.playstation.com/api/pdp-redirect/?locale=de-de&id=PSD001-PSDE01840_63-PS5GRADEDCEC7XZE",
    "https://www.playstation.com/api/pdp-redirect/?locale=de-de&id=PSD001-PSDE01929_59-PS5CONSOLETAPQ3E",
]

# Keywords that indicate refurbished / graded units
REFURBISHED_KEYWORDS = [
    "generalüberholt",
    "zertifiziert",
    "graded",
    "refurbished",
]

# Keywords for add-to-cart buttons
CART_BUTTON_KEYWORDS = [
    "in den einkaufswagen",
    "hinzufügen",
    "add to cart",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------
# Data Model
# ---------------------------------------------------------
@dataclass
class ItemStatus:
    input_url: str
    final_url: str
    title: str
    is_refurbished: bool
    price: Optional[float]
    price_raw: Optional[str]
    in_stock: bool
    button_label: Optional[str] = None


# ---------------------------------------------------------
# Price Parsing Helper
# ---------------------------------------------------------
def parse_german_price(price_text: str) -> Optional[float]:
    """
    Parses German price strings (e.g. '549,99 €', '€549,99', '549 €', '649,00 €')
    into a float value.
    """
    if not price_text:
        return None

    # Matches patterns like '€549,99', '549,99 €', '€ 549', '549 €'
    match = re.search(r"(?:€\s*([\d\.,]+)|([\d\.,]+)\s*€)", price_text)
    if not match:
        return None

    raw_num = match.group(1) or match.group(2)
    # Strip spaces
    raw_num = raw_num.strip()

    # German formatting handles thousand dots and decimal commas (e.g., 1.234,56 or 549,99)
    if "," in raw_num and "." in raw_num:
        raw_num = raw_num.replace(".", "").replace(",", ".")
    elif "," in raw_num:
        raw_num = raw_num.replace(",", ".")

    try:
        return float(raw_num)
    except ValueError:
        return None


# ---------------------------------------------------------
# Telegram Notification
# ---------------------------------------------------------
def send_telegram_alert(item: ItemStatus) -> bool:
    """
    Sends an HTML-formatted alert via Telegram if bot token and chat ID are configured.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.warning(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured; skipping Telegram notification."
        )
        return False

    condition_text = "Refurbished / Graded" if item.is_refurbished else "Brand New"
    price_text = f"{item.price:.2f} €" if item.price is not None else (item.price_raw or "Unknown")

    message_html = (
        f"🚨 <b>PS5 In-Stock Alert!</b>\n\n"
        f"<b>Product:</b> {html.escape(item.title)}\n"
        f"<b>Price:</b> {html.escape(price_text)}\n"
        f"<b>Condition:</b> {html.escape(condition_text)}\n"
        f"<b>URL:</b> <a href=\"{html.escape(item.final_url)}\">Direct Link</a>\n"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info("Telegram notification sent successfully.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram notification: {e}")
        return False


# ---------------------------------------------------------
# Page Scraper & Evaluation
# ---------------------------------------------------------
def check_url(page, url: str) -> ItemStatus:
    """
    Navigates to the PlayStation Direct URL using Playwright, waits for JS hydration,
    and extracts title, refurbished status, price, and stock status.
    """
    logger.info(f"Navigating to: {url}")
    # Navigate and wait for DOM content loaded and network idle
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        logger.warning(f"Initial navigation warning: {e}")

    # Wait for hydration/network settling
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    final_url = page.url
    page_title = page.title()

    # Extract Product Title / H1
    h1_elements = page.locator("h1").all_inner_texts()
    title = h1_elements[0].strip() if h1_elements else page_title

    # 1. Refurbished / Graded Detection
    # Check both input URL and final redirected URL, title, and product badges
    combined_header_text = f"{url} {final_url} {title}".lower()
    is_refurbished = any(kw in combined_header_text for kw in REFURBISHED_KEYWORDS)

    # Also check prominent badges or tags in main container if not yet detected
    if not is_refurbished:
        badges = page.locator("main [class*='badge'], main [class*='tag'], main [data-qa*='badge']").all_inner_texts()
        badge_text = " ".join(badges).lower()
        if any(kw in badge_text for kw in REFURBISHED_KEYWORDS):
            is_refurbished = True

    # Strategy A: Check card matching the current title or exact final URL path
    from urllib.parse import urlparse
    current_path = urlparse(final_url).path.rstrip("/")

    parsed_price = None
    price_raw = None

    price_cards = page.locator("[data-qa*='display-price']").all()
    for pel in price_cards:
        try:
            txt = pel.inner_text().strip()
            if "€" in txt:
                card = pel.locator("xpath=./ancestor::a | ./ancestor::div[contains(@class, 'card')]")
                if card.count() > 0:
                    href = (card.first.get_attribute("href") or "").rstrip("/")
                    card_txt = card.first.inner_text().strip()
                    # Check exact path match or title in card text
                    if (href and href == current_path) or (title and title.lower() in card_txt.lower()):
                        p_val = parse_german_price(txt)
                        if p_val is not None:
                            parsed_price = p_val
                            price_raw = txt
                            break
        except Exception:
            continue

    # Strategy B: Fallback to any visible display-price
    if parsed_price is None:
        for pel in price_cards:
            try:
                if pel.is_visible():
                    txt = pel.inner_text().strip()
                    p_val = parse_german_price(txt)
                    if p_val is not None:
                        parsed_price = p_val
                        price_raw = txt
                        break
            except Exception:
                continue

    # Strategy C: Fallback to generic price selectors or body regex
    if parsed_price is None:
        generic_prices = page.locator("[class*='price'], [data-qa*='price']").all()
        for gp in generic_prices:
            try:
                if gp.is_visible():
                    txt = gp.inner_text().strip()
                    p_val = parse_german_price(txt)
                    if p_val is not None:
                        parsed_price = p_val
                        price_raw = txt
                        break
            except Exception:
                continue

    # 3. Stock Detection
    # Look for visible and enabled buttons matching add to cart keywords
    in_stock = False
    matching_button_label = None

    buttons = page.locator("button, a[role='button'], input[type='button'], input[type='submit']").all()
    for btn in buttons:
        try:
            if not btn.is_visible():
                continue
            
            # Check inner text and aria-label
            btn_text = btn.inner_text().strip()
            aria_label = btn.get_attribute("aria-label") or ""
            combined_btn_desc = f"{btn_text} {aria_label}".lower()

            # Ignore generic header cart buttons (e.g. aria-label="Einkaufswagen")
            if combined_btn_desc.strip() in ["einkaufswagen", "cart"]:
                continue

            # Match against cart button keywords
            if any(kw in combined_btn_desc for kw in CART_BUTTON_KEYWORDS):
                if btn.is_enabled():
                    in_stock = True
                    matching_button_label = btn_text or aria_label
                    break
        except Exception:
            continue

    return ItemStatus(
        input_url=url,
        final_url=final_url,
        title=title,
        is_refurbished=is_refurbished,
        price=parsed_price,
        price_raw=price_raw,
        in_stock=in_stock,
        button_label=matching_button_label,
    )


# ---------------------------------------------------------
# Main Execution
# ---------------------------------------------------------
def main():
    logger.info("Starting PS5 stock and price monitor...")
    alerts_triggered = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="de-DE",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )

        for idx, url in enumerate(TARGET_URLS, 1):
            logger.info("=" * 60)
            logger.info(f"Checking Item {idx}/{len(TARGET_URLS)}")
            page = context.new_page()

            try:
                item = check_url(page, url)

                # Format log output
                condition = "Refurbished / Graded" if item.is_refurbished else "Brand New"
                stock_str = "IN STOCK" if item.in_stock else "OUT OF STOCK"
                price_str = f"{item.price:.2f} €" if item.price is not None else (item.price_raw or "N/A")

                logger.info(f"  Title:        {item.title}")
                logger.info(f"  Condition:    {condition}")
                logger.info(f"  Stock Status: {stock_str}" + (f" (Button: '{item.button_label}')" if item.button_label else ""))
                logger.info(f"  Price:        {price_str}")
                logger.info(f"  Final URL:    {item.final_url}")

                # Filtering Rules:
                # 1. Target: Brand-new PS5 Disc Edition
                # 2. Ignore refurbished/graded units
                # 3. Only alert if price <= 650.0 EUR (or price cannot be parsed while clearly in stock)
                if item.is_refurbished:
                    logger.info("  Filter Decision: SKIPPED (Refurbished/Graded unit).")
                    continue

                if not item.in_stock:
                    logger.info("  Filter Decision: SKIPPED (Item out of stock).")
                    continue

                # Stock is True and Brand-New is True
                if item.price is not None and item.price > TARGET_MAX_PRICE:
                    logger.info(f"  Filter Decision: SKIPPED (Price {item.price:.2f} € exceeds {TARGET_MAX_PRICE} € threshold).")
                    continue

                logger.info("  Filter Decision: MATCH FOUND! Alerting via Telegram...")
                send_telegram_alert(item)
                alerts_triggered += 1

            except Exception as e:
                logger.error(f"Error checking {url}: {e}", exc_info=True)
            finally:
                page.close()

        browser.close()

    logger.info("=" * 60)
    logger.info(f"Monitoring completed. {alerts_triggered} alert(s) sent.")


if __name__ == "__main__":
    main()
