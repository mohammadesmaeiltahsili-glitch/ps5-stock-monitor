# PS5 Stock & Price Monitor (PlayStation Direct Germany)

Automated Python bot that monitors PlayStation Direct Germany for brand-new PlayStation 5 Disc Edition consoles under 650 EUR and sends instant Telegram notifications. Runs 24/7 on GitHub Actions with zero local infrastructure needed.

## Features
- **Headless Browser Rendering**: Uses Playwright Chromium with realistic macOS user-agent and `de-DE` locale to bypass anti-bot challenges and wait for client-side React hydration.
- **Strict Quality Filter**: Automatically detects and ignores refurbished, graded, and certified units (`Generalüberholt`, `Zertifiziert`, `GRADED`).
- **German Price Parsing**: Accurately parses German currency formats (e.g. `549,99 €`, `649,99 €`) and alerts only if price is <= 650.00 EUR (or if in-stock without visible price).
- **Stock Detection**: Checks for visible and enabled Add-to-Cart buttons (`In den Einkaufswagen`, `Hinzufügen`, `Add to Cart`).
- **Automated Monitoring**: GitHub Actions workflow runs every 5 minutes (`*/5 * * * *`) with manual dispatch support.

## Monitored URLs
1. [PS5 Disc Console (1 TB)](https://www.playstation.com/api/pdp-redirect/?locale=de-de&id=PSD001-PSDE01929_59-PS5CONSOLEHB2OYE)
2. [PS5 Slim (Certified Refurbished)](https://www.playstation.com/api/pdp-redirect/?locale=de-de&id=PSD001-PSDE00233_59-PS5GRADEDCLIZSLE)
3. [PS5 Original (Certified Refurbished)](https://www.playstation.com/api/pdp-redirect/?locale=de-de&id=PSD001-PSDE01840_63-PS5GRADEDCEC7XZE)
4. [PS5 Disc + DualSense Controller Bundle](https://www.playstation.com/api/pdp-redirect/?locale=de-de&id=PSD001-PSDE01929_59-PS5CONSOLETAPQ3E)

## Setup & Deployment

### 1. Telegram Bot Setup
1. Chat with [@BotFather](https://t.me/BotFather) on Telegram and run `/newbot` to create your bot and obtain your `TELEGRAM_BOT_TOKEN`.
2. Start a conversation with your bot (or add it to a channel/group), and find your Chat ID (e.g. via [@userinfobot](https://t.me/userinfobot) or `https://api.telegram.org/bot<TOKEN>/getUpdates`).

### 2. GitHub Actions Secrets
In your GitHub repository:
1. Navigate to **Settings** > **Secrets and variables** > **Actions**.
2. Click **New repository secret** and add:
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
   - `TELEGRAM_CHAT_ID`: Your numerical Telegram chat ID.

The workflow will immediately start running every 5 minutes. You can also trigger it manually under the **Actions** tab by selecting **PS5 Stock & Price Monitor** and clicking **Run workflow**.

### 3. Local Dry-Run Testing
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Copy and fill your local environment secrets
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

# Run monitor
python check_ps5.py
```
