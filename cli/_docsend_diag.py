"""Diag v2 — anti-WAF + form-scoped gate selectors + post-submit DOM dump."""
from playwright.sync_api import sync_playwright
import sys, time

URL = sys.argv[1]
EMAIL = sys.argv[2]
PASSCODE = sys.argv[3]
OUT_DIR = "io/humain/deals/ImmuneCo/inputs"

REAL_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = browser.new_context(
        viewport={"width": 1600, "height": 1100},
        device_scale_factor=2,
        user_agent=REAL_UA,
        locale="en-US",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle", timeout=30000)

    page.screenshot(path=f"{OUT_DIR}/_diag_01_initial.png", full_page=True)
    print(f"URL: {page.url}  Title: {page.title()!r}")

    # Form-scoped fills
    em = page.locator("input[name='link_auth_form[email]']").first
    em.fill(EMAIL)
    print(f"  filled email → link_auth_form[email]")
    pc = page.locator("input[name='link_auth_form[passcode]']").first
    pc.fill(PASSCODE)
    print(f"  filled passcode → link_auth_form[passcode]")
    page.screenshot(path=f"{OUT_DIR}/_diag_02_filled.png", full_page=True)

    # Submit: click the Continue button inside the auth form specifically
    try:
        page.locator("form#new_link_auth_form button[type=submit]").first.click(timeout=3000)
        print("  clicked form#new_link_auth_form button[type=submit]")
    except Exception as e:
        print(f"  ! submit click failed: {e}")
    page.wait_for_load_state("networkidle", timeout=20000)
    time.sleep(2)
    page.screenshot(path=f"{OUT_DIR}/_diag_03_post_submit.png", full_page=True)
    print(f"\nPost-submit URL: {page.url}  Title: {page.title()!r}")

    # What's on the page now?
    print("--- iframes ---")
    for f in page.frames:
        print(f"  {f.url}")
    print("--- all img tags (first 10) ---")
    for el in page.query_selector_all("img")[:10]:
        print(f"  src={(el.get_attribute('src') or '')[:80]} class={el.get_attribute('class')!r}")
    print("--- all canvas tags ---")
    for el in page.query_selector_all("canvas"):
        print(f"  class={el.get_attribute('class')!r} id={el.get_attribute('id')!r}")
    print("--- elements with 'page' or 'slide' or 'view' in class ---")
    for el in page.query_selector_all("[class*=page], [class*=slide], [class*=preso], [class*=view]")[:15]:
        tag = el.evaluate("el => el.tagName")
        cls = el.get_attribute("class") or ""
        print(f"  <{tag.lower()}> class={cls[:100]!r}")
    print("--- error / blocked text? ---")
    body = page.locator("body").inner_text()[:500]
    print(f"  body[:500] = {body!r}")
    browser.close()
