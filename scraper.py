#!/usr/bin/env python3
import asyncio
import json
import re
import os
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urlparse
import time
import random # For random delays, proxy choice, etc.

# --- START: Configuration for Login (User specific) ---
# IMPORTANT: For real use, consider environment variables or a secure config file
ALIBABA_USERNAME = os.environ.get("ALIBABA_USER") # Example: export ALIBABA_USER="your_email@example.com"
ALIBABA_PASSWORD = os.environ.get("ALIBABA_PASS") # Example: export ALIBABA_PASS="your_password"
# If not using environment variables, you can hardcode them for testing (NOT RECOMMENDED FOR PRODUCTION)
# ALIBABA_USERNAME = "your_email@example.com"
# ALIBABA_PASSWORD = "your_password"

LOGIN_URL = "https://login.alibaba.com" # Or the specific login entry point you prefer
# --- END: Configuration for Login ---

# --- START: Functions for Enhanced Browser Context and Anti-Bot Evasion ---

async def apply_stealth_techniques(page_or_context):
    """Apply stealth techniques to the page or context via add_init_script."""
    script = """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
        configurable: true
    });
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            return [
                {
                    0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                    description: "Portable Document Format",
                    filename: "internal-pdf-viewer",
                    length: 1,
                    name: "Chrome PDF Plugin"
                },
                {
                    0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                    description: "Portable Document Format",
                    filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                    length: 1,
                    name: "Chrome PDF Viewer"
                },
                {
                    0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable"},
                    1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable"},
                    description: "Native Client",
                    filename: "internal-nacl-plugin",
                    length: 2,
                    name: "Native Client"
                }
            ];
        }
    });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true
    });
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8, // Example value, can be randomized or set based on common configurations
        configurable: true
    });
    window.chrome = {
        app: {
            isInstalled: false,
            InstallState: {
                DISABLED: 'disabled',
                INSTALLED: 'installed',
                NOT_INSTALLED: 'not_installed'
            },
            RunningState: {
                CANNOT_RUN: 'cannot_run',
                READY_TO_RUN: 'ready_to_run',
                RUNNING: 'running'
            }
        },
        runtime: {
            OnInstalledReason: {
                CHROME_UPDATE: 'chrome_update',
                INSTALL: 'install',
                SHARED_MODULE_UPDATE: 'shared_module_update',
                UPDATE: 'update'
            },
            OnRestartRequiredReason: {
                APP_UPDATE: 'app_update',
                OS_UPDATE: 'os_update',
                PERIODIC: 'periodic'
            },
            PlatformArch: {
                ARM: 'arm',
                ARM64: 'arm64',
                MIPS: 'mips',
                MIPS64: 'mips64',
                X86_32: 'x86-32',
                X86_64: 'x86-64'
            },
            PlatformNaclArch: {
                ARM: 'arm',
                MIPS: 'mips',
                MIPS64: 'mips64',
                X86_32: 'x86-32',
                X86_64: 'x86-64'
            },
            PlatformOs: {
                ANDROID: 'android',
                CROS: 'cros',
                LINUX: 'linux',
                MAC: 'mac',
                OPENBSD: 'openbsd',
                WIN: 'win'
            },
            RequestUpdateCheckStatus: {
                NO_UPDATE: 'no_update',
                THROTTLED: 'throttled',
                UPDATE_AVAILABLE: 'update_available'
            }
        }
    };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
    const nativeToString = Function.prototype.toString;
    Function.prototype.toString = function() {
        if (this === Function.prototype.toString) return nativeToString.call(nativeToString);
        if (this === Function.prototype.valueOf) return nativeToString.call(Function.prototype.valueOf);
        return nativeToString.call(this);
    };
    """
    await page_or_context.add_init_script(script)
    print("Stealth techniques applied via add_init_script.")


async def create_enhanced_browser_context(playwright, output_dir, storage_state_path=None, headless_mode=True, proxy_config=None):
    """Creates an enhanced browser context, potentially loading a storage state."""
    print(f"Attempting to launch browser (headless: {headless_mode})")
    browser_launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--window-size=1920,1080',
            '--start-maximized',
            '--disable-notifications',
            '--disable-extensions',
        ]
    if headless_mode:
        browser_launch_args.append('--hide-scrollbars')

    browser = await playwright.chromium.launch(
        headless=headless_mode,
        args=browser_launch_args
    )

    loaded_storage_state = None
    effective_storage_state_path_to_load = storage_state_path
    
    # Corrected logic: Only try to load if a path is actually given for loading state
    if effective_storage_state_path_to_load and os.path.exists(effective_storage_state_path_to_load):
        try:
            with open(effective_storage_state_path_to_load, 'r') as f:
                loaded_storage_state = json.load(f)
            print(f"Successfully loaded previous storage state from {effective_storage_state_path_to_load}")
        except Exception as e:
            print(f"Error loading storage state from {effective_storage_state_path_to_load}: {e}. Will proceed without it.")
            loaded_storage_state = None # Ensure it's None if loading fails
    elif effective_storage_state_path_to_load: # Path given but doesn't exist
         print(f"Storage state file not found at {effective_storage_state_path_to_load}. A new context will be created without loading state.")
    else: # No path provided at all (storage_state_path was None and no default was set)
        print("No storage state path provided for loading. A new context will be created without loading state for this instance.")


    context_options = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "geolocation": {"latitude": 40.730610, "longitude": -73.935242},
        "permissions": ["geolocation"],
        "color_scheme": "light",
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
        "java_script_enabled": True,
        "accept_downloads": False,
        "ignore_https_errors": False,
        "bypass_csp": False,
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="121", "Google Chrome";v="121", "Not;A=Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        },
        "storage_state": loaded_storage_state
    }

    if proxy_config:
        context_options["proxy"] = proxy_config
        print(f"Using proxy: {proxy_config['server']}")

    context = await browser.new_context(**context_options)
    await apply_stealth_techniques(context)

    page = await context.new_page()

    page.set_default_navigation_timeout(120000)
    page.set_default_timeout(60000)

    original_general_storage_state_path = os.path.join(output_dir, "storage_state.json")

    print(f"Enhanced browser context and page created. Headless: {headless_mode}, Storage State Loaded: {loaded_storage_state is not None}")
    return browser, context, page, original_general_storage_state_path


async def simulate_human_behavior(page):
    """Simulates some human-like interactions on the page."""
    print("Simulating human behavior...")
    await page.wait_for_timeout(random.randint(500, 2000))

    if random.random() > 0.6:
        print("  Simulating a small scroll wheel action.")
        try:
            await page.mouse.wheel(0, random.randint(50, 200))
            await page.wait_for_timeout(random.randint(300, 800))
        except Exception as e:
            print(f"  Error during mouse wheel: {e}")
    print("Finished simulating human behavior.")

async def diagnose_page_version(page, output_dir, diagnosis_name="page_diagnosis"):
    """Saves HTML, screenshot, and metrics for diagnostics."""
    # This function definition remains, but calls to it will be removed from the main flow.
    print(f"Diagnosing page version: {diagnosis_name}")
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            print(f"Error creating diagnostic output directory {output_dir}: {e}")
            return None

    html_path = os.path.join(output_dir, f"{diagnosis_name}.html")
    try:
        html_content = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"  HTML content saved to {html_path}")
    except Exception as e:
        print(f"  Error saving HTML content: {e}")

    screenshot_path = os.path.join(output_dir, f"{diagnosis_name}.png")
    try:
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"  Screenshot saved to {screenshot_path}")
    except Exception as e:
        print(f"  Error saving screenshot: {e}")

    metrics = None
    try:
        metrics = await page.evaluate("""() => {
            return {
                windowInnerHeight: window.innerHeight,
                windowInnerWidth: window.innerWidth,
                documentHeight: document.body.scrollHeight,
                userAgent: navigator.userAgent,
                webdriver: navigator.webdriver,
                pluginsLength: navigator.plugins.length,
                languages: navigator.languages,
                platform: navigator.platform,
                deviceMemory: navigator.deviceMemory || 'N/A',
                hardwareConcurrency: navigator.hardwareConcurrency,
                isSimplifiedVersion: document.body.classList.contains('mobile') ||
                                     document.body.classList.contains('simplified') ||
                                     document.documentElement.classList.contains('mobile')
            };
        }""")
        print(f"  Page metrics: {json.dumps(metrics, indent=2)}")

        metrics_path = os.path.join(output_dir, f"{diagnosis_name}_metrics.json")
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
        print(f"  Metrics saved to {metrics_path}")
    except Exception as e:
        print(f"  Error extracting/saving page metrics: {e}")

    print(f"Diagnostic files attempt finished for {output_dir}")
    return metrics

# --- END: Functions for Enhanced Browser Context ---

# --- Function to handle manual login ---
async def perform_manual_login_and_save_state(playwright, output_dir, storage_state_path_for_saving):
    """
    Guides the user through a manual login process and saves the authentication state.
    """
    print("\n--- Starting Manual Login Process ---")
    print(f"Login required. Storage state for saving: {storage_state_path_for_saving}")
    print("A browser window will open. Please log in to Alibaba.")

    browser, context, page, _ = await create_enhanced_browser_context(
        playwright,
        output_dir,
        storage_state_path=None,
        headless_mode=False
    )

    try:
        main_page_url = "https://www.alibaba.com"
        print(f"Navigating to Alibaba homepage: {main_page_url} ...")
        await page.goto(main_page_url, wait_until="networkidle", timeout=90000)
        print("Current URL after homepage load:", page.url)
        
        await handle_modal_dialogs(page)
        await page.wait_for_timeout(random.randint(1500,2500))

        login_button_selectors = [
            "a[href*='login.alibaba.com']",
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]",
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'log in')]",
            "div[data-spm-anchor-id*='sign']", 
            ".header-sign-btn",
            "#header-sign-in-btn",
            "a[data-val*='login']"
        ]
        login_clicked = False
        for sel in login_button_selectors:
            try:
                print(f"Attempting to find login button with selector: {sel}")
                login_btn = page.locator(sel).first
                if await login_btn.is_visible(timeout=5000):
                    print(f"  Login button visible. Attempting to click...")
                    await login_btn.click(timeout=10000)
                    await page.wait_for_load_state("networkidle", timeout=45000)
                    print("  Current URL after clicking login button:", page.url)
                    login_clicked = True
                    break
                else:
                    print(f"  Login button {sel} not visible.")
            except PlaywrightTimeoutError:
                print(f"  Timeout finding or clicking login button {sel}.")
            except Exception as e:
                print(f"  Error with login button {sel}: {e}")
        
        if not login_clicked:
            print("Could not automatically click a login button on the homepage. Navigating to direct LOGIN_URL.")
            print(f"Navigating to Alibaba login page: {LOGIN_URL} ...")
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=90000)
            print("  Current URL after direct LOGIN_URL attempt:", page.url)
        
        await handle_modal_dialogs(page)

        print("\n**********************************************************************")
        print("PLEASE MANUALLY LOG IN using the browser window that has opened.")
        print("Ensure you are on your main account page or a product page after login.")
        print("After you have successfully logged in and the page has loaded,")
        print("RETURN TO THIS CONSOLE and press Enter to continue.")
        print("**********************************************************************")
        input("Press Enter to continue after logging in...")

        await context.storage_state(path=storage_state_path_for_saving)
        print(f"Authentication state saved to {storage_state_path_for_saving}")
        print("Login successful and state saved.")
        return True

    except PlaywrightTimeoutError as e:
        print(f"Timeout during manual login process: {e}")
        # Optionally, keep one diagnostic call for critical errors if desired
        # if page: await diagnose_page_version(page, output_dir, "login_timeout_page_critical")
        return False
    except Exception as e:
        print(f"An error occurred during the manual login process: {e}")
        # if page: await diagnose_page_version(page, output_dir, "login_error_page_critical")
        return False
    finally:
        if browser.is_connected():
            await browser.close()
            print("Browser closed after manual login attempt.")


async def handle_modal_dialogs(page):
    """Checks for and attempts to close known modal dialogs."""
    print("Checking for modal dialogs...")
    try:
        modal_mask_selector = "div.baxia-dialog-mask"
        modal_close_button_selectors = [
            "div.baxia-dialog-header-close",
            "button[aria-label='close']",
            "button[class*='close']",
            "span[class*='close']",
            ".baxia-dialog-close",
            ".next-dialog-close"
        ]
        generic_overlay_selector = "div[class*='overlay'][style*='display: block'], div[class*='mask'][style*='display: block']"

        active_modal_element = None
        modal_mask = await page.query_selector(modal_mask_selector)
        if modal_mask and await modal_mask.is_visible(timeout=1000):
            print("Modal dialog mask detected (baxia-dialog-mask).")
            active_modal_element = modal_mask
        else:
            generic_overlay = await page.query_selector(generic_overlay_selector)
            if generic_overlay and await generic_overlay.is_visible(timeout=1000):
                print("Generic overlay/mask detected.")
                active_modal_element = generic_overlay
            else:
                print("No obvious modal dialogs detected by primary selectors.")
                cookie_accept_buttons = [
                    "button:has-text('Accept All')", "button:has-text('Agree')", "button:has-text('Accept')",
                    "button:has-text('OK')", "button[id*='cookie-accept']", "button[class*='cookie-accept']",
                    "button:has-text('Allow all cookies')", "button:has-text('I understand')"
                ]
                for btn_selector in cookie_accept_buttons:
                    try:
                        button = page.locator(btn_selector).first
                        if await button.is_visible(timeout=1500):
                            print(f"Attempting to click cookie consent button: {btn_selector}")
                            await button.click(timeout=3000)
                            await page.wait_for_timeout(1000)
                            print("Cookie consent likely handled.")
                            return True
                    except PlaywrightTimeoutError:
                        pass 
                    except Exception as e:
                        print(f"Error clicking cookie button {btn_selector}: {e}")
                return False

        print("Attempting to close modal/overlay...")
        closed = False
        for btn_selector in modal_close_button_selectors:
            try:
                close_button = page.locator(btn_selector).first
                if await close_button.is_visible(timeout=2000):
                    print(f"Attempting to click close button with selector: {btn_selector}")
                    await close_button.click(timeout=5000)
                    await page.wait_for_timeout(2000)

                    if active_modal_element and not await active_modal_element.is_visible(timeout=2000):
                        print("Modal/Overlay dialog closed successfully after clicking.")
                        closed = True
                        break
                    else:
                        modal_mask_after = await page.query_selector(modal_mask_selector)
                        generic_overlay_after = await page.query_selector(generic_overlay_selector)
                        if not ((modal_mask_after and await modal_mask_after.is_visible(timeout=1000)) or \
                                (generic_overlay_after and await generic_overlay_after.is_visible(timeout=1000))):
                            print("Modal/Overlay dialog closed successfully (re-check).")
                            closed = True
                            break
                        else:
                            print(f"Modal/Overlay mask still visible after clicking {btn_selector}.")
            except PlaywrightTimeoutError:
                print(f"Close button {btn_selector} not visible or interactable in time.")
            except Exception as e:
                print(f"Error clicking close button {btn_selector}: {e}")
            if closed: break

        if not closed:
            print("Could not close modal/overlay by clicking known buttons. Attempting to press Escape key.")
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(2000)
                if active_modal_element and not await active_modal_element.is_visible(timeout=2000):
                    print("Modal/Overlay dialog closed successfully with Escape key.")
                    closed = True
                else:
                    modal_mask_after_esc = await page.query_selector(modal_mask_selector)
                    generic_overlay_after_esc = await page.query_selector(generic_overlay_selector)
                    if not ((modal_mask_after_esc and await modal_mask_after_esc.is_visible(timeout=1000)) or \
                            (generic_overlay_after_esc and await generic_overlay_after_esc.is_visible(timeout=1000))):
                        print("Modal/Overlay dialog closed successfully with Escape key (re-check).")
                        closed = True
                    else:
                        print("Failed to close modal/overlay dialog with Escape key. It might still be present.")
            except Exception as e:
                print(f"Error pressing Escape key: {e}")

        if closed: return True
        print("Modal handling attempted but modal might still be present.")
        return False
    except Exception as e:
        print(f"Error during modal handling: {e}")
    return False

async def scrape_products_from_current_page(page, scroll_delay, max_products_per_category, current_category_name, known_product_urls, max_scroll_attempts_no_new_content=3, output_dir="."):
    products_in_category_for_return = []
    print(f"Starting scrape for category: {current_category_name}")

    scroll_attempts_no_new_content = 0
    total_scroll_limit = 30
    scroll_count = 0

    product_container_selector = "div.hugo4-pc-grid-item"

    NON_PRODUCT_TITLES = [
        "safe & easy payments", "money-back policy", "shipping & logistics services",
        "after-sales protections", "rising search trends", "trade assurance",
        "on-time delivery", "product monitoring & inspection services", "logistics service",
        "payment solution", "view more", "learn more", "shop now", "explore",
        "alibaba.com selects", "source now", "send inquiry", "chat now", "contact supplier",
        "get a quote", "supplier assessment"
    ]

    while scroll_count < total_scroll_limit:
        scroll_count += 1
        print(f"Processing product extraction pass {scroll_count} for category '{current_category_name}'...")

        container_elements_before_scroll = await page.query_selector_all(product_container_selector)
        count_before_scroll = len(container_elements_before_scroll)
        print(f"  Product container count before scroll/extraction (pass {scroll_count}): {count_before_scroll}")

        current_body_scroll_height = await page.evaluate("document.body.scrollHeight")

        if scroll_count > 1:
            print("  Attempting to focus body and scroll...")
            try:
                await page.focus("body")
                print("  Successfully focused body.")
            except Exception as e:
                print(f"  Could not focus body, proceeding with scroll anyway: {e}")

            js_scroll_distance = await page.evaluate("window.innerHeight * 0.85")
            print(f"  Attempting JavaScript scroll by {js_scroll_distance}px")
            await page.evaluate(f"window.scrollBy(0, {js_scroll_distance})")
            await page.wait_for_timeout(random.randint(400, 700))

            print("  Attempting PageDown key presses...")
            for i in range(random.randint(8, 15)):
                await page.keyboard.press("PageDown")
                await page.wait_for_timeout(random.randint(250, 450))
                if (i + 1) % 5 == 0:
                    print(f"     ... {i+1} PageDowns done")
            await page.wait_for_timeout(random.randint(1200, 2000))
            print("  Finished scroll attempts.")
        else:
            print(f"  Initial product extraction pass (scroll_count=1), using pre-loaded content.")

        effective_wait_after_scroll_actions = scroll_delay + random.randint(1, 4)
        print(f"  Waiting for ~{effective_wait_after_scroll_actions} seconds for content to potentially load/settle after scroll/initial load...")
        await page.wait_for_timeout(effective_wait_after_scroll_actions * 1000)

        new_content_appeared_in_dom = False
        if scroll_count > 1:
            print(f"  Checking if new product containers appeared in DOM (start count: {count_before_scroll}). Max wait 10s...")
            try:
                await page.wait_for_function(
                    f"document.querySelectorAll('{product_container_selector}').length > {count_before_scroll}",
                    timeout=10000
                )
                new_total_container_count = len(await page.query_selector_all(product_container_selector))
                print(f"  SUCCESS: Product container count increased to {new_total_container_count}.")
                new_content_appeared_in_dom = True
            except PlaywrightTimeoutError:
                new_total_container_count = len(await page.query_selector_all(product_container_selector))
                print(f"  TIMEOUT/INFO: Product container count did not increase after scroll. Current count: {new_total_container_count}.")
            except Exception as e:
                print(f"  Error during wait_for_function for product container count: {e}")

        current_container_elements = await page.query_selector_all(product_container_selector)
        print(f"  Extracting product information from {len(current_container_elements)} found containers for category: {current_category_name} (Pass {scroll_count})...")

        new_products_found_this_scroll_pass = []

        for i, container_el in enumerate(current_container_elements):
            product_data = {
                "name": None, "product_url": None, "image_url": None, "price": None,
                "alibaba_category": current_category_name
            }
            try:
                link_el = await container_el.query_selector("a[href*='/product-detail/']")
                if not link_el:
                    link_el = await container_el.query_selector("a[href]")
                if not link_el:
                    continue

                raw_product_url = await link_el.get_attribute("href")
                if raw_product_url:
                    parsed_url = urlparse(raw_product_url)
                    if parsed_url.scheme and parsed_url.netloc:
                        product_data["product_url"] = raw_product_url
                    elif raw_product_url.startswith("//"):
                        product_data["product_url"] = "https:" + raw_product_url
                    elif raw_product_url.startswith("/"):
                        current_page_url_parts = urlparse(page.url)
                        product_data["product_url"] = f"{current_page_url_parts.scheme}://{current_page_url_parts.netloc}{raw_product_url}"
                    elif "http" in raw_product_url:
                         product_data["product_url"] = raw_product_url
                    else:
                        continue
                else:
                    continue

                if not product_data["product_url"] or "javascript:void(0)" in product_data["product_url"]:
                    continue

                if product_data["product_url"] in known_product_urls:
                    continue

                is_duplicate_this_pass_batch = any(
                    p_temp["product_url"] == product_data["product_url"] for p_temp in new_products_found_this_scroll_pass
                )
                if is_duplicate_this_pass_batch:
                    continue

                if not (re.search(r"/product-detail/|/p-detail/|/product_detail\.htm|item_detail\.htm", product_data["product_url"], re.IGNORECASE) or
                            ".html" in product_data["product_url"].lower()):
                    promo_keywords = ['promotion', 'campaign', 'service', 'solution', 'about', 'contact', 'policy', 'news', 'blog', 'category', 'search', 'company_profile', 'list', 'collection', 'supplier']
                    if any(kw in product_data["product_url"].lower() for kw in promo_keywords):
                        continue

                img_el_candidate = await container_el.query_selector("img[data-src], img[src]")
                if img_el_candidate:
                    img_src = await img_el_candidate.get_attribute("data-src") or await img_el_candidate.get_attribute("src")
                    if img_src:
                        if img_src.startswith("//"): product_data["image_url"] = "https:" + img_src
                        elif img_src.startswith("/"):
                            base_url_parts = urlparse(page.url)
                            product_data["image_url"] = f"{base_url_parts.scheme}://{base_url_parts.netloc}{img_src}"
                        elif img_src.startswith("http"): product_data["image_url"] = img_src

                name_text_content = None
                name_selectors_relative = [
                    "h2", "h3", ".product-title", ".item-title", ".title", ".name",
                    "div[class*='title'] span", "div[class*='subject'] span", "a[title]"
                ]
                name_el_to_check = link_el
                if name_el_to_check:
                        name_text_content = await name_el_to_check.get_attribute("title")
                        if not name_text_content or len(name_text_content.strip()) < 5:
                            name_text_content = await name_el_to_check.text_content()

                if not name_text_content or len(name_text_content.strip()) < 10 :
                    for sel in name_selectors_relative:
                        name_el = await container_el.query_selector(sel)
                        if name_el:
                            name_text_content_candidate = await name_el.get_attribute("title") or await name_el.text_content()
                            if name_text_content_candidate and len(name_text_content_candidate.strip()) > (len(name_text_content or "") or 5):
                                name_text_content = name_text_content_candidate
                                if len(name_text_content.strip()) > 10: break

                if name_text_content:
                    cleaned_name = name_text_content.strip()
                    cleaned_name = re.sub(r'Min\.\s*order:.*', '', cleaned_name, flags=re.IGNORECASE | re.DOTALL).strip()
                    cleaned_name = re.sub(r'\$\s?[\d,.]+(\.\d{1,2})?\s*(-\s*\$\s?[\d,.]+(\.\d{1,2})?)?(/\s*\w+)?', '', cleaned_name).strip()
                    cleaned_name = re.sub(r'\d+(\.\d+)?\s*(pieces|sets|pairs|units|meters|kgs?|tons?|pcs|Yards?).*', '', cleaned_name, flags=re.IGNORECASE | re.DOTALL).strip()
                    cleaned_name = re.sub(r'(Ready to Ship|In stock|Listed in last \d+ days|Hot sale|New arrival)', '', cleaned_name, flags=re.IGNORECASE).strip()
                    cleaned_name = re.sub(r'\s{2,}', ' ', cleaned_name).strip()

                    if any(non_prod_title.lower() in cleaned_name.lower() for non_prod_title in NON_PRODUCT_TITLES if len(cleaned_name.split()) < 7):
                        cleaned_name = None
                    elif len(cleaned_name) < 10 or len(cleaned_name) > 250:
                        cleaned_name = None
                    elif ("alibaba.com" in cleaned_name.lower() or "supplier" in cleaned_name.lower() or "wholesale" in cleaned_name.lower()) and len(cleaned_name.split()) < 7 :
                        cleaned_name = None
                    product_data["name"] = cleaned_name

                price_text_found = None
                price_selectors_relative = [
                    ".price", ".product-price", ".item-price",
                    "div[class*='price']", "span[class*='price']"
                ]
                for sel in price_selectors_relative:
                    price_el = await container_el.query_selector(sel)
                    if price_el:
                        price_text_found_candidate = await price_el.text_content()
                        if price_text_found_candidate and re.search(r"[$€£¥]", price_text_found_candidate):
                            price_text_found = price_text_found_candidate
                            break
                if price_text_found and re.search(r"\d", price_text_found):
                    match = re.search(r"([$€£¥\s?[\d,]+(\.\d{1,2})?)", price_text_found)
                    if match: product_data["price"] = match.group(1).strip()

                if product_data["name"] and product_data["product_url"] and product_data["image_url"] and product_data["price"]:
                    new_products_found_this_scroll_pass.append(product_data)

            except Exception as e:
                continue

        actual_newly_added_this_pass_count = 0
        if not new_products_found_this_scroll_pass and len(current_container_elements) > 0 and scroll_count == 1:
            print(f"  INFO: Found {len(current_container_elements)} containers, but extracted 0 new unique products with current sub-selectors on pass 1.")

        for p_new in new_products_found_this_scroll_pass:
            products_in_category_for_return.append(p_new)
            known_product_urls.add(p_new["product_url"])
            actual_newly_added_this_pass_count += 1
            print(f"Scraped new product {len(products_in_category_for_return)}/'{max_products_per_category if max_products_per_category else 'all new'}' for '{current_category_name}': Name='{p_new['name'][:30]}...' Price='{p_new['price']}'")

        if max_products_per_category and len(products_in_category_for_return) >= max_products_per_category:
            print(f"Reached max_products_per_category limit of {max_products_per_category} for '{current_category_name}'.")
            break

        new_body_scroll_height_after_extraction = await page.evaluate("document.body.scrollHeight")
        if actual_newly_added_this_pass_count == 0:
            condition_no_new_dom_and_height = (scroll_count > 1 and not new_content_appeared_in_dom and new_body_scroll_height_after_extraction <= current_body_scroll_height + 20)
            condition_initial_fail_with_containers = (scroll_count == 1 and len(current_container_elements) > 0 and not new_products_found_this_scroll_pass)
            condition_initial_no_containers = (scroll_count == 1 and len(current_container_elements) == 0)

            if condition_no_new_dom_and_height or condition_initial_fail_with_containers or condition_initial_no_containers:
                scroll_attempts_no_new_content += 1
                if condition_no_new_dom_and_height:
                    print(f"  No new unique products, no new DOM elements, AND page height similar. Attempt {scroll_attempts_no_new_content}/{max_scroll_attempts_no_new_content}.")
                elif condition_initial_fail_with_containers:
                    print(f"  Found containers on initial load but extracted 0 new unique products. Attempt {scroll_attempts_no_new_content}/{max_scroll_attempts_no_new_content}.")
                elif condition_initial_no_containers:
                    print(f"  No product containers found on initial load. Attempt {scroll_attempts_no_new_content}/{max_scroll_attempts_no_new_content}.")
            elif scroll_count > 1 and new_content_appeared_in_dom:
                scroll_attempts_no_new_content += 1
                print(f"  New product containers appeared, but current sub-selectors didn't extract new valid unique products. Attempt {scroll_attempts_no_new_content}/{max_scroll_attempts_no_new_content}.")
            else:
                scroll_attempts_no_new_content += 1
                print(f"  No new unique products scraped. Page height changed: {new_body_scroll_height_after_extraction > current_body_scroll_height + 20}. New DOM elements: {new_content_appeared_in_dom}. Attempt {scroll_attempts_no_new_content}/{max_scroll_attempts_no_new_content}.")

            if scroll_attempts_no_new_content >= max_scroll_attempts_no_new_content:
                print(f"Reached end of new products for category '{current_category_name}' after {scroll_attempts_no_new_content} scrolls with no new valid content or significant DOM/page changes.")
                break
        else:
            scroll_attempts_no_new_content = 0
            print(f"  Successfully added {actual_newly_added_this_pass_count} new unique products this pass.")

        if scroll_count >= total_scroll_limit:
            print(f"Reached total scroll limit of {total_scroll_limit} for category '{current_category_name}'.")
            break

    print(f"Finished scraping for category: {current_category_name}. Found {len(products_in_category_for_return)} new unique products this session.")
    return products_in_category_for_return


async def scrape_alibaba_new_arrivals(url, output_dir, category_toggles, known_product_urls, storage_state_path_for_login, max_products_per_category=None, scroll_delay=5, max_scroll_no_new=3, use_proxy=False, force_login_flow=False):
    all_new_products_this_session = []
    browser = None
    context = None
    page = None
    abs_output_dir = os.path.abspath(output_dir)

    async with async_playwright() as p:
        proxy_config = None
        if use_proxy:
            print("Proxy usage requested, but example proxy list is commented out. Configure proxies if needed.")

        if force_login_flow or not os.path.exists(storage_state_path_for_login):
            if force_login_flow:
                print("Force login flow is enabled.")
            else:
                print(f"Storage state file '{storage_state_path_for_login}' not found for login.")

            login_success = await perform_manual_login_and_save_state(p, abs_output_dir, storage_state_path_for_login)
            if not login_success:
                print("Manual login failed or was aborted. Exiting scraper.")
                return []
            print("Login state should now be saved. Proceeding with scraping using the new state...")
        else:
            print(f"Found existing login state file: {storage_state_path_for_login}. Attempting to use it.")

        try:
            browser, context, page, general_session_storage_path = await create_enhanced_browser_context(
                p,
                abs_output_dir,
                storage_state_path=storage_state_path_for_login,
                headless_mode=True, # Set to False for debugging logged-in state
                proxy_config=proxy_config
            )

            print(f"Navigating to {url} with potentially logged-in context...")
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            print("Page loaded. Waiting for initial dynamic content and potential modals...")
            await page.wait_for_timeout(random.randint(10000, 18000))
            
            # Verification step (optional, can be commented out once confirmed working)
            print("--- VERIFYING LOGIN STATE ---")
            login_button_selector_verify = "a:has-text('Sign In')" 
            account_element_selector_verify = "div.tnh-ma"

            is_login_button_visible = await page.is_visible(login_button_selector_verify, timeout=3000)
            is_account_element_visible = await page.is_visible(account_element_selector_verify, timeout=3000)

            if is_account_element_visible and not is_login_button_visible:
                print("VERIFICATION: Logged-in state appears CONFIRMED (account element found, Sign In button not found).")
            elif is_login_button_visible:
                print("VERIFICATION: Logged-out state detected (Sign In button is visible). Login might have failed or session expired.")
            else:
                print("VERIFICATION: Login state UNCERTAIN (neither definitive login nor logout element clearly found by simple check).")
            print("--- END LOGIN VERIFICATION ---")

            await handle_modal_dialogs(page)
            await page.wait_for_timeout(random.randint(1500, 3500))

            category_tab_selector = "div.hugo-dotelement.tab-item"
            initial_category_tabs_elements = await page.query_selector_all(category_tab_selector)

            if not initial_category_tabs_elements:
                print("No category tabs found using primary selector. Trying alternative selectors...")
                potential_tab_selectors = [
                    "div[role='tab']", "li[role='tab']", "a[role='tab']",
                    "div[class*='tab-item']", "div[class*='category-tab']",
                    ".scc-tab-item", ".rax-scrollview-horizontal > div > div"
                ]
                for sel in potential_tab_selectors:
                    print(f"  Trying alternative tab selector: {sel}")
                    candidate_tabs = await page.query_selector_all(sel)
                    if candidate_tabs:
                        temp_tabs = []
                        for tab_el in candidate_tabs:
                            try:
                                if not await tab_el.is_visible(timeout=1000): continue
                                text_content = (await tab_el.text_content() or "").strip()
                                if text_content and len(text_content) > 1 and len(text_content) < 50:
                                    bounding_box = await tab_el.bounding_box()
                                    if bounding_box and bounding_box['width'] > 10 and bounding_box['height'] > 5:
                                        temp_tabs.append(tab_el)
                            except Exception: pass
                        if temp_tabs:
                            initial_category_tabs_elements = temp_tabs
                            print(f"Found {len(initial_category_tabs_elements)} potential tabs with selector: {sel}")
                            category_tab_selector = sel
                            break

            if not initial_category_tabs_elements:
                print("Still no category tabs found after trying alternatives. Scraping current view as 'All' category.")
                if category_toggles.get("All", False):
                    products_from_page = await scrape_products_from_current_page(page, scroll_delay, max_products_per_category, "All", known_product_urls, max_scroll_no_new, abs_output_dir)
                    all_new_products_this_session.extend(products_from_page)
                else:
                    print("Category 'All' is not enabled in toggles. Skipping.")
            else:
                print(f"Found {len(initial_category_tabs_elements)} category tabs using selector '{category_tab_selector}'.")
                category_names_and_indices = []
                for i, tab_element in enumerate(initial_category_tabs_elements):
                    try:
                        cat_name_candidate_element = await tab_element.query_selector(".text") or \
                                                     await tab_element.query_selector("span") or \
                                                     tab_element
                        cat_name = (await cat_name_candidate_element.text_content() or "").strip()
                        cat_name = re.sub(r"^\d+\s*-\s*", "", cat_name).strip()
                        cat_name = re.sub(r"\s{2,}", " ", cat_name).strip()

                        if cat_name:
                            base_name = cat_name
                            occurrence = 1
                            temp_check_name = cat_name
                            while any(c["name_on_page"] == temp_check_name for c in category_names_and_indices):
                                occurrence += 1
                                temp_check_name = f"{base_name}_{occurrence}"

                            category_names_and_indices.append({
                                "name_for_toggle": base_name,
                                "name_on_page": temp_check_name,
                                "original_index": i
                            })
                            print(f"Identified category tab: '{base_name}' (Unique ID for run: '{temp_check_name}', Original Index: {i})")
                        else:
                            print(f"Warning: Tab at original index {i} has no discernible text name. Skipping.")
                    except Exception as e:
                        print(f"Error getting name for tab at original index {i}: {e}")

                if not category_names_and_indices:
                        print("No valid category names extracted from tabs. Scraping current view as 'All' if enabled.")
                        if category_toggles.get("All", False):
                            products_from_page = await scrape_products_from_current_page(page, scroll_delay, max_products_per_category, "All", known_product_urls, max_scroll_no_new, abs_output_dir)
                            all_new_products_this_session.extend(products_from_page)
                        else:
                            print("Category 'All' is not enabled in toggles. Skipping.")
                else:
                    first_category_processed = False
                    for cat_info in category_names_and_indices:
                        current_category_name_for_toggle = cat_info["name_for_toggle"]
                        current_category_name_on_page = cat_info["name_on_page"]
                        original_tab_index = cat_info["original_index"]

                        is_enabled = category_toggles.get(current_category_name_for_toggle, False)
                        if not is_enabled:
                            for toggle_key, toggle_value in category_toggles.items():
                                if toggle_value and toggle_key.lower().replace('&', 'and') == current_category_name_for_toggle.lower().replace('&', 'and'):
                                    is_enabled = True
                                    print(f"Matched '{current_category_name_for_toggle}' to toggle '{toggle_key}' via flexible matching.")
                                    break

                        if not is_enabled:
                            print(f"Category '{current_category_name_for_toggle}' (from page: '{current_category_name_on_page}') is not enabled in toggles or no match found. Skipping.")
                            continue

                        print(f"\nProcessing category: '{current_category_name_on_page}' (Original Tab Index: {original_tab_index})...")

                        await handle_modal_dialogs(page)

                        current_tabs_on_page = await page.query_selector_all(category_tab_selector)
                        if original_tab_index >= len(current_tabs_on_page):
                            print(f"Tab for '{current_category_name_on_page}' (index {original_tab_index}) no longer found. DOM might have changed. Skipping.")
                            continue

                        tab_to_click = current_tabs_on_page[original_tab_index]
                        try:
                            await tab_to_click.scroll_into_view_if_needed(timeout=10000)
                            await page.wait_for_timeout(random.randint(800,1500))

                            class_attr = (await tab_to_click.get_attribute("class") or "").lower()
                            aria_selected = (await tab_to_click.get_attribute("aria-selected") or "").lower()
                            is_selected_class_names = ["item-selected", "active", "current", "is-active", "is-selected", "tab-active"]
                            is_selected = any(sel_class in class_attr for sel_class in is_selected_class_names) or aria_selected == "true"

                            action_taken = False
                            if not (original_tab_index == 0 and not first_category_processed and is_selected) and not is_selected :
                                print(f"Attempting to click tab: '{current_category_name_on_page}'")
                                await tab_to_click.click(timeout=20000, force=True)
                                print(f"Clicked '{current_category_name_on_page}'. Waiting for content to load...")
                                action_taken = True
                            elif is_selected:
                                print(f"Tab '{current_category_name_on_page}' appears to be already selected.")
                            else:
                                print(f"First tab '{current_category_name_on_page}' assumed selected or will be processed without click.")

                            first_category_processed = True

                            if action_taken:
                                print("Waiting after tab click (networkidle and fixed delay)...")
                                try:
                                    await page.wait_for_load_state('networkidle', timeout=35000)
                                except PlaywrightTimeoutError:
                                    print("Network idle timed out after tab click, proceeding with fixed wait.")
                                await page.wait_for_timeout(random.randint(7000, 12000))
                            else:
                                print("Tab was pre-selected/first or did not require click. Performing a shorter wait...")
                                await page.wait_for_timeout(random.randint(4000, 7000))

                            await handle_modal_dialogs(page)

                        except PlaywrightTimeoutError as te:
                            print(f"Timeout error during tab interaction or loading for '{current_category_name_on_page}': {te}. Attempting page reload.")
                            try:
                                await page.reload(wait_until="domcontentloaded", timeout=60000)
                                await page.wait_for_timeout(random.randint(8000,12000))
                                await handle_modal_dialogs(page)
                            except Exception as rle:
                                print(f"Error during reload/modal handling after tab click timeout: {rle}")
                            print(f"Skipping category '{current_category_name_on_page}' due to persistent click/load issues.")
                            continue
                        except Exception as e:
                            print(f"Non-timeout error during tab interaction for '{current_category_name_on_page}': {e}. Skipping category.")
                            continue

                        products_from_category = await scrape_products_from_current_page(page, scroll_delay, max_products_per_category, current_category_name_on_page, known_product_urls, max_scroll_no_new, abs_output_dir)
                        all_new_products_this_session.extend(products_from_category)
                        print(f"Total new unique products scraped so far this session: {len(all_new_products_this_session)}")

            if context and general_session_storage_path:
                print(f"Attempting to save general browser session state to {general_session_storage_path}")
                try:
                    await context.storage_state(path=general_session_storage_path)
                    print(f"General browser session state saved successfully to {general_session_storage_path}")
                except Exception as e:
                    print(f"Error saving general browser session state: {e}")

        except PlaywrightTimeoutError as pte:
            print(f"A major Playwright timeout occurred during the scraping process: {pte}")
        except Exception as e:
            print(f"An critical error occurred during the overall scraping process: {e}")

        finally:
            if browser and browser.is_connected():
                print("Closing browser...")
                await browser.close()
            print(f"Browser closed. Total new unique products scraped in this session: {len(all_new_products_this_session)}")

    return all_new_products_this_session

# --- START: Category Configuration ---
CATEGORY_TOGGLES = {
    "All": False,
    "Mother, Kids & Toys": False,
    "Purchasing agent": False,
    "Consumer Electronics": True, # Enabled for testing
    "Packaging & Printing": False,
    "Gifts & Crafts": False,
    "Electronic Components, Accessories & Telecommunications": False,
    "Electronic Components, Accessories and Telecommunications": False,
    "Beauty": False,
    "Jewelry, Eyewear, Watches & Accessories": False,
    "Jewelry, Eyewear, Watches and Accessories": False,
    "Personal Care & Household Cleaning": False,
    "Personal Care and Household Cleaning": False,
    "Apparel & Accessories": False,
    "Apparel and Accessories": False,
    "Home & Garden": False,
    "Home and Garden": False,
    "Sports & Entertainment": False,
    "Sports and Entertainment": False,
    "Shoes & Accessories": False,
    "Shoes and Accessories": False,
    "Luggage, Bags & Cases": False,
    "Luggage, Bags and Cases": False,
    "Home Appliances": False,
    "Pet Supplies": False,
    "Furniture": False,
    "Tools & Hardware": False,
    "Tools and Hardware": False,
    "Medical devices & Supplies": False,
    "Medical devices and Supplies": False,
    "Agriculture": False,
    "Business Services": False,
    "Chemicals": False,
    "Commercial Equipment & Machinery": False,
    "Commercial Equipment and Machinery": False,
    "Construction & Building Machinery": False,
    "Construction and Building Machinery": False,
    "Construction & Real Estate": False,
    "Construction and Real Estate": False,
    "Electrical Equipment & Supplies": False,
    "Electrical Equipment and Supplies": False,
    "Environment": False,
    "Fabric & Textile Raw Material": False,
    "Fabric and Textile Raw Material": False,
    "Fabrication Services": False,
    "Food & Beverage": False,
    "Food and Beverage": False,
    "Industrial Machinery": False,
    "Lights & Lighting": False,
    "Lights and Lighting": False,
    "Material Handling": False,
    "Metals & Alloys": False,
    "Metals and Alloys": False,
    "Power Transmission": False,
    "Renewable Energy": False,
    "Rubber & Plastics": False,
    "Rubber and Plastics": False,
    "Safety": False,
    "School & Office Supplies": False,
    "School and Office Supplies": False,
    "Security": False,
    "Testing Instrument & Equipment": False,
    "Testing Instrument and Equipment": False,
    "Vehicle Parts & Accessories": False,
    "Vehicle Parts and Accessories": False,
    "Vehicles & Transportation": False,
    "Vehicles and Transportation": False
}
# --- END: Category Configuration ---

async def main():
    target_url = "https://sale.alibaba.com/p/db971rh77/index.html"

    OUTPUT_DIRECTORY = r"C:\Users\zdoes\Downloads\alibaba_explorer" # !!! ENSURE THIS PATH IS CORRECT FOR YOUR SYSTEM !!!
    abs_output_dir = os.path.abspath(OUTPUT_DIRECTORY)

    json_output_filename = "scraped_alibaba_new_arrivals_enhanced.json"
    json_output_path = os.path.join(abs_output_dir, json_output_filename)

    auth_storage_state_filename = "alibaba_auth_state.json"
    auth_storage_state_path = os.path.join(abs_output_dir, auth_storage_state_filename)

    existing_products = []
    known_product_urls = set()

    if not os.path.exists(abs_output_dir):
        try:
            os.makedirs(abs_output_dir)
            print(f"Created output directory: {abs_output_dir}")
        except OSError as e:
            print(f"Error creating output directory {abs_output_dir}: {e}")
            print("Please ensure the path is correct and you have permissions, or change OUTPUT_DIRECTORY in the script.")
            return

    if os.path.exists(json_output_path):
        try:
            with open(json_output_path, "r", encoding="utf-8") as f:
                existing_products = json.load(f)
                for product in existing_products:
                    if isinstance(product, dict) and "product_url" in product and product["product_url"]:
                        known_product_urls.add(product["product_url"])
                print(f"Loaded {len(existing_products)} products from {json_output_path}. Found {len(known_product_urls)} unique existing product URLs.")
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {json_output_path}. Will start with an empty list and overwrite if new data is scraped.")
            existing_products = []
            known_product_urls = set()
    else:
        print(f"Output file {json_output_path} does not exist. Will create a new one.")

    print(f"Starting multi-category scraper with enhanced context for {target_url}")
    print(f"Output files will be saved to: {abs_output_dir}")
    print(f"Authentication state will be managed using: {auth_storage_state_path}")


    selected_categories_to_scrape = [cat for cat, is_selected in CATEGORY_TOGGLES.items() if is_selected]
    if not selected_categories_to_scrape:
        print("No categories are currently selected in CATEGORY_TOGGLES. Please enable at least one.")
        return
    else:
        print(f"Will attempt to scrape the following categories if found on page: {', '.join(selected_categories_to_scrape)}")


    FORCE_RELOGIN = False
    # FORCE_RELOGIN = True # Uncomment to force login flow

    scraped_data_current_session = await scrape_alibaba_new_arrivals(
        url=target_url,
        output_dir=abs_output_dir,
        category_toggles=CATEGORY_TOGGLES,
        known_product_urls=known_product_urls,
        storage_state_path_for_login=auth_storage_state_path,
        max_products_per_category=None, 
        scroll_delay=random.randint(6, 9),
        max_scroll_no_new=2,
        use_proxy=False,
        force_login_flow=FORCE_RELOGIN
    )

    if scraped_data_current_session:
        print(f"\nSuccessfully scraped {len(scraped_data_current_session)} new unique products in this session.")
        final_product_list = existing_products + scraped_data_current_session
        try:
            with open(json_output_path, "w", encoding="utf-8") as f:
                json.dump(final_product_list, f, indent=2, ensure_ascii=False)
            print(f"Combined data (total {len(final_product_list)} products) saved to {json_output_path}")

            print(f"\n--- Summary of first 3 newly scraped products this session (if available) ---")
            for i, product in enumerate(scraped_data_current_session[:3]):
                print(f"--- New Product {i+1} (Category: {product.get('alibaba_category', 'N/A')}) ---")
                print(f"  Name: {product.get('name', 'N/A')}")
                print(f"  URL: {product.get('product_url', 'N/A')}")
                print(f"  Price: {product.get('price', 'N/A')}")
                print(f"  Image: {product.get('image_url', 'N/A')}")
                print("---------------------")
        except Exception as e:
            print(f"Error writing to JSON file: {e}")
    elif not scraped_data_current_session and existing_products:
         print("\nNo new unique products were scraped in this session.")
         try:
            with open(json_output_path, "w", encoding="utf-8") as f:
                json.dump(existing_products, f, indent=2, ensure_ascii=False)
            print(f"Existing data (total {len(existing_products)} products) re-saved to {json_output_path} as no new products were found.")
         except Exception as e:
            print(f"Error re-writing existing data to JSON file: {e}")
    else:
        print("No products were scraped in this session, and no existing products were loaded.")

if __name__ == "__main__":
    asyncio.run(main())