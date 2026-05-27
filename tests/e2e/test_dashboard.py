import pytest
import time
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:3000"

def login(page: Page):
    page.goto(BASE_URL)
    page.wait_for_selector("input[type='email']", timeout=10000)
    page.fill("input[type='email']", "manish@marketpulse.in")
    page.fill("input[type='password']", "demo123")
    page.click("button[type='submit']")
    # Wait for header to appear after login
    page.wait_for_selector("text=NIFTY", timeout=15000)
    time.sleep(1)

def test_login_flow(page: Page):
    page.goto(BASE_URL)
    page.wait_for_selector("input[type='email']")
    page.fill("input[type='email']", "manish@marketpulse.in")
    page.fill("input[type='password']", "demo123")
    page.click("button[type='submit']")
    page.wait_for_selector("text=NIFTY", timeout=15000)
    expect(page.locator("text=Watchlist").first).to_be_visible()
    print("Login flow: PASSED")

def test_nifty_ticker_visible(page: Page):
    login(page)
    expect(page.locator("text=NIFTY").first).to_be_visible()
    expect(page.locator("text=SENSEX").first).to_be_visible()
    print("Market tickers: PASSED")

def test_watchlist_shows_stocks(page: Page):
    login(page)
    time.sleep(2)
    expect(page.locator("text=Watchlist").first).to_be_visible()
    print("Watchlist visible: PASSED")

def test_signals_tab(page: Page):
    login(page)
    time.sleep(2)
    # Click first stock in watchlist
    page.locator("text=INFY").first.click()
    time.sleep(1)
    page.locator("text=Signals").click()
    time.sleep(2)
    expect(page.locator("text=Signal History").first).to_be_visible()
    print("Signals tab: PASSED")

def test_calendar_tab(page: Page):
    login(page)
    time.sleep(2)
    page.locator("text=Calendar").click()
    time.sleep(2)
    expect(page.locator("text=RESULTS CALENDAR").first).to_be_visible()
    print("Calendar tab: PASSED")