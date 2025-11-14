import re
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


driver_dir = Path("YOUR CHROMEDRIVE DIR PATH HERE")
driver_path = driver_dir / "chromedriver"
from selenium.webdriver.chrome.service import Service
service = Service(str(driver_path))
driver = webdriver.Chrome(service=service)

def extract_actor_id(url):
    """
    Extract the actor ID from an IMDb URL.
    
    Args:
        url: IMDb actor URL (e.g., https://www.imdb.com/name/nm0000138/)
    
    Returns:
        str: Actor ID (e.g., 'nm0000138')
    """
    # Pattern to match IMDb actor ID (nm followed by 7-8 digits)
    pattern = r'/name/(nm\d{7,8})'
    match = re.search(pattern, url)
    
    if match:
        return match.group(1)
    else:
        raise ValueError(f"Could not extract actor ID from URL: {url}")


def setup_driver(headless=True):
    """
    Set up and return a Chrome WebDriver instance.
    Automatically downloads and manages ChromeDriver using webdriver-manager.
    
    Args:
        headless: Whether to run browser in headless mode (default: True)
    
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver
    """
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    
    # Use webdriver-manager to automatically handle ChromeDriver
    service = Service(str(driver_path))
    driver = webdriver.Chrome(service=service, options=chrome_options)
    # service = Service(ChromeDriverManager().install())
    # driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def download_imdb_actor(url, output_dir="movies", headless=True, wait_time=10):
    """
    Download an IMDb actor page with full credits by clicking the "All credits" link.
    
    Args:
        url: IMDb actor URL (e.g., https://www.imdb.com/name/nm0000138/)
        output_dir: Base directory for saving actors (default: 'movies')
        headless: Whether to run browser in headless mode (default: True)
        wait_time: Maximum time to wait for elements to load (default: 10 seconds)
    
    Returns:
        str: Path to the saved HTML file
    """
    # Extract actor ID from URL
    actor_id = extract_actor_id(url)
    
    # Create directory structure: movies/actors/{actor_id}/
    actor_dir = Path(output_dir) / "actors" / actor_id
    actor_dir.mkdir(parents=True, exist_ok=True)
    
    # Set up WebDriver
    driver = None
    try:
        print(f"Setting up browser for actor ID: {actor_id}")
        driver = setup_driver(headless=headless)
        
        # Navigate to the actor page first
        print(f"Navigating to actor page: {url}")
        driver.get(url)
        
        # Wait for the page to fully load
        print("Waiting for page to load...")
        wait = WebDriverWait(driver, wait_time)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # Wait for JavaScript to finish executing
        print("Waiting for JavaScript to finish...")
        time.sleep(5)  # Give extra time for JavaScript to render
        
        # Accept cookies if cookie banner appears
        print("Checking for cookie banner...")
        try:
            # Common cookie accept button selectors
            cookie_selectors = [
                "//button[contains(text(), 'Accept')]",
                "//button[contains(text(), 'Accept All')]",
                "//button[contains(text(), 'I Accept')]",
                "//a[contains(text(), 'Accept')]",
                "//button[@id='accept']",
                "//button[contains(@class, 'accept')]",
                "//button[contains(@id, 'accept')]",
            ]
            
            cookie_accepted = False
            for selector in cookie_selectors:
                try:
                    cookie_button = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    print("Found cookie banner, accepting cookies...")
                    driver.execute_script("arguments[0].click();", cookie_button)
                    time.sleep(2)
                    cookie_accepted = True
                    print("✓ Cookies accepted")
                    break
                except (TimeoutException, NoSuchElementException):
                    continue
            
            if not cookie_accepted:
                print("No cookie banner found (or already accepted)")
        except Exception as e:
            print(f"Could not handle cookie banner: {e}")
        
        # Wait for document ready state
        ready_state = driver.execute_script("return document.readyState")
        print(f"Document ready state: {ready_state}")
        time.sleep(2)
        
        # Scroll down to find the Credits section
        print("Scrolling to find Credits section...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
        time.sleep(2)
        
        # Count elements in credits section BEFORE clicking "All credits"
        print("\n" + "="*60)
        print("COUNTING ELEMENTS IN CREDITS SECTION (BEFORE 'All credits')")
        print("="*60)
        before_count = 0
        before_movie_links = 0
        try:
            # Try to find credits section
            credits_sections = driver.find_elements(By.XPATH, "//section[contains(@class, 'ipc-page-section')]")
            print(f"Found {len(credits_sections)} section(s) with ipc-page-section class")
            
            # Count all links in credits area
            all_links_before = driver.find_elements(By.XPATH, "//a[contains(@href, '/title/tt')]")
            before_movie_links = len(all_links_before)
            print(f"Movie links found BEFORE clicking 'All credits': {before_movie_links}")
            
            # Count elements in credits section
            for section in credits_sections:
                section_links = section.find_elements(By.XPATH, ".//a[contains(@href, '/title/tt')]")
                before_count += len(section_links)
            
            print(f"Total movie links in credits sections: {before_count}")
        except Exception as e:
            print(f"Error counting elements before: {e}")
        
        print("="*60 + "\n")
        
        # Try to find and click the "All credits" link
        credits_clicked = False
        
        # Strategy 1: Look for the "All credits" button/link (prioritize data-testid)
        try:
            # Try to find the "All credits" button/link by various methods
            # PRIORITY: Use the specific data-testid attribute first
            all_credits_selectors = [
                # Most specific: data-testid attribute (this is the correct one!)
                "//button[@data-testid='nm-flmg-all-credits']",
                "//*[@data-testid='nm-flmg-all-credits']",
                # Button with specific classes and text
                "//button[contains(@class, 'ipc-link') and contains(@class, 'ipc-link--base') and contains(text(), 'All credits')]",
                "//button[contains(@class, 'ipc-link') and normalize-space(text())='All credits']",
                # Button with text "All credits"
                "//button[normalize-space(text())='All credits']",
                "//button[contains(text(), 'All credits')]",
                # Link with text "All credits"
                "//a[normalize-space(text())='All credits']",
                "//a[contains(text(), 'All credits')]",
                # Exact text match (case insensitive) for links
                "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'all credits')]",
                # Contains href with credits
                "//a[contains(@href, '#credits')]",
                "//a[contains(@href, '/name/') and contains(@href, '#credits')]",
                # Fallback: any element containing "All credits"
                "//*[contains(text(), 'All credits')]/ancestor::button[1]",
                "//*[contains(text(), 'All credits')]/ancestor::a[1]",
            ]
            
            # First try CSS selector for the specific data-testid (most reliable)
            try:
                element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-testid='nm-flmg-all-credits']")))
                print(f"Found 'All credits' button using CSS selector: button[data-testid='nm-flmg-all-credits']")
                found_via_css = True
            except (TimeoutException, NoSuchElementException):
                found_via_css = False
                element = None
            
            # If CSS selector didn't work, try XPath selectors
            if not found_via_css:
                for selector in all_credits_selectors:
                    try:
                        # Wait for element to be present
                        element = wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                        print(f"Found 'All credits' link using XPath selector: {selector}")
                        break
                    except (TimeoutException, NoSuchElementException):
                        continue
                else:
                    # No element found with any selector
                    element = None
            
            if element is not None:
                # Scroll to element to ensure it's visible
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", element)
                time.sleep(1.5)
                
                # Try multiple click strategies
                click_success = False
                
                # Strategy 1: Try JavaScript click (bypasses overlays)
                try:
                    driver.execute_script("arguments[0].click();", element)
                    click_success = True
                    print("Successfully clicked 'All credits' button using JavaScript")
                except Exception as js_error:
                    print(f"JavaScript click failed: {js_error}")
                    
                    # Strategy 2: Try regular click
                    try:
                        # Wait for element to be clickable
                        element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='nm-flmg-all-credits']")))
                        element.click()
                        click_success = True
                        print("Successfully clicked 'All credits' button using regular click")
                    except Exception as reg_error:
                        print(f"Regular click failed: {reg_error}")
                        
                        # Strategy 3: Try ActionChains click
                        try:
                            from selenium.webdriver.common.action_chains import ActionChains
                            actions = ActionChains(driver)
                            actions.move_to_element(element).pause(0.5).click().perform()
                            click_success = True
                            print("Successfully clicked 'All credits' button using ActionChains")
                        except Exception as ac_error:
                            print(f"ActionChains click failed: {ac_error}")
                
                if click_success:
                    credits_clicked = True
                    # Wait for the page to update after clicking
                    print("Successfully clicked 'All credits' button. Waiting for credits to load...")
                    time.sleep(5)  # Initial wait for AJAX request to start
                    
                    # Wait for URL to change or for credits content to appear
                    try:
                        # Check if URL changed or if we're on a different page
                        current_url = driver.current_url
                        if '#credits' in current_url or 'credits' in current_url.lower():
                            print("URL indicates credits page loaded")
                    except:
                        pass
            else:
                print("Could not find 'All credits' button with any selector")
            
            # If clicking failed, try navigating directly to the credits URL
            if not credits_clicked:
                print("Clicking failed, navigating directly to #credits URL...")
                credits_url = f"{url}#credits"
                driver.get(credits_url)
                time.sleep(5)
                credits_clicked = True
            
            # Wait for the credits content to fully load
            print("Waiting for all credits content to load...")
            
            # Wait for network requests to complete by checking for specific elements
            try:
                # Wait for credits section to appear
                wait.until(EC.presence_of_element_located((By.XPATH, "//section[contains(@class, 'ipc-page-section')]")))
                print("Credits section detected")
            except TimeoutException:
                print("Warning: Credits section not found, but continuing...")
            
            # Wait for JavaScript/AJAX to finish loading content
            print("Waiting for dynamic content to load...")
            time.sleep(5)
            
            # Check if page is still loading
            for i in range(3):
                try:
                    # Check if there are loading indicators
                    loading_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'loading') or contains(@class, 'spinner')]")
                    if not loading_elements:
                        break
                    print(f"Still loading... waiting (attempt {i+1}/3)")
                    time.sleep(3)
                except:
                    break
            
            # Scroll multiple times to trigger lazy loading of all credits
            print("Scrolling to trigger lazy loading of all credits...")
            scroll_pause_time = 2
            
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)
            
            # Scroll to top
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # Scroll to middle
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(scroll_pause_time)
            
            # Scroll to bottom again
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)
            
            # Scroll back to top
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # Scroll to bottom one more time to ensure everything is loaded
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)
            
            # Wait for any remaining AJAX/network requests
            print("Waiting for network requests to complete...")
            time.sleep(5)
            
            # # Verify content has loaded by checking for movie links
            # # Also check for a specific movie ID to ensure credits are fully loaded
            # verification_movie_id = "tt0190196"
            # verification_found = False
            # max_retries = 5
            # retry_count = 0
            
            # while not verification_found and retry_count < max_retries:
            #     try:
            #         movie_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/title/tt')]")
            #         print(f"Found {len(movie_links)} movie links on the page")
                    
            #         # Check if the verification movie ID is present
            #         page_source = driver.page_source
            #         if verification_movie_id in page_source:
            #             verification_found = True
            #             print(f"✓ Verification movie ID {verification_movie_id} found in page content")
            #         else:
            #             print(f"✗ Verification movie ID {verification_movie_id} not found yet (attempt {retry_count + 1}/{max_retries})")
                        
            #             if retry_count < max_retries - 1:
            #                 # Scroll again and wait
            #                 print("Scrolling and waiting for more content to load...")
            #                 driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            #                 time.sleep(3)
            #                 driver.execute_script("window.scrollTo(0, 0);")
            #                 time.sleep(2)
            #                 driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            #                 time.sleep(3)
                    
            #         if len(movie_links) > 0:
            #             print("Movie links detected")
            #         else:
            #             print("Warning: No movie links found")
                        
            #     except Exception as e:
            #         print(f"Warning: Could not verify movie links: {e}")
                
            #     retry_count += 1
            
            # if not verification_found:
            #     print(f"WARNING: Verification movie ID {verification_movie_id} was not found after {max_retries} attempts")
            #     print("The credits may not be fully loaded. Continuing anyway...")
            # else:
            #     print("✓ All credits appear to be loaded successfully")
            
            # # Final wait to ensure everything is settled
            # print("Final wait to ensure all content is loaded...")
            # time.sleep(3)
            
        except Exception as e:
            print(f"Warning: Could not click 'All credits' link: {e}")
            print("Attempting to proceed with current page content...")
            import traceback
            traceback.print_exc()
        
        # Count elements in credits section AFTER clicking "All credits"
        print("\n" + "="*60)
        print("COUNTING ELEMENTS IN CREDITS SECTION (AFTER 'All credits')")
        print("="*60)
        after_count = 0
        after_movie_links = 0
        try:
            # Count all links in credits area
            all_links_after = driver.find_elements(By.XPATH, "//a[contains(@href, '/title/tt')]")
            after_movie_links = len(all_links_after)
            print(f"Movie links found AFTER clicking 'All credits': {after_movie_links}")
            
            # Count elements in credits section
            credits_sections = driver.find_elements(By.XPATH, "//section[contains(@class, 'ipc-page-section')]")
            for section in credits_sections:
                section_links = section.find_elements(By.XPATH, ".//a[contains(@href, '/title/tt')]")
                after_count += len(section_links)
            
            print(f"Total movie links in credits sections: {after_count}")
            
            # Compare before and after
            print("\n" + "-"*60)
            print("COMPARISON:")
            print("-"*60)
            print(f"Movie links BEFORE: {before_movie_links}")
            print(f"Movie links AFTER:  {after_movie_links}")
            difference = after_movie_links - before_movie_links
            print(f"Difference: {difference} links")
            
            if difference > 0:
                print(f"✓ SUCCESS: Credits section expanded! {difference} additional movie links loaded.")
            elif difference == 0:
                print("⚠ WARNING: No additional links found. Credits may not have expanded.")
            else:
                print("⚠ WARNING: Fewer links found after clicking. Something may have gone wrong.")
            print("="*60 + "\n")
            
        except Exception as e:
            print(f"Error counting elements after: {e}")
            import traceback
            traceback.print_exc()
        
        # Get the page source after clicking
        html_content = driver.page_source
        
        # # Verify the specific movie ID is present in the HTML
        # verification_movie_id = "tt0190196"
        # if verification_movie_id in html_content:
        #     print(f"✓ Verification: Movie ID {verification_movie_id} is present in the HTML")
        # else:
        #     print(f"✗ WARNING: Movie ID {verification_movie_id} is NOT present in the HTML")
        #     print("The credits may not be fully loaded. Consider re-running the script.")
        
        # Count movie links to verify we got the full credits
        movie_link_count = len(re.findall(r'/title/tt\d{7,8}', html_content))
        print(f"Found {movie_link_count} movie links in the HTML")

        if movie_link_count >= after_movie_links:
            print(f"✓ SUCCESS: {movie_link_count} movie links found in the HTML")
        else:
            print(f"✗ WARNING: {movie_link_count} movie links found in the HTML, expected {after_movie_links}")
            print("The page may not have fully loaded. Try increasing wait_time or check the page manually.")
        
        # Count unique movie IDs
        unique_movie_ids = set(re.findall(r'/title/(tt\d{7,8})', html_content))
        print(f"Found {len(unique_movie_ids)} unique movie IDs in the HTML")
        
        # if movie_link_count < 45:
        #     print(f"Warning: Expected at least 45 movie links, but found only {movie_link_count}")
        #     print("The page may not have fully loaded. Try increasing wait_time or check the page manually.")
        
        # Save the HTML content
        html_file = actor_dir / "actor.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Successfully saved HTML to: {html_file}")
        return str(html_file)
        
    except Exception as e:
        print(f"Error downloading the actor page: {e}")
        raise
    finally:
        if driver:
            driver.quit()
            print("Browser closed")


def main():
    """
    Main function to run the script from command line.
    """
    import sys
    
    # if len(sys.argv) < 2:
    #     print("Usage: python download_imdb_actor.py <imdb_actor_url> [output_dir] [--headless]")
    #     print("Example: python download_imdb_actor.py https://www.imdb.com/name/nm0000138/")
    #     print("Options:")
    #     print("  --headless: Run browser in headless mode (default is visible)")
    #     sys.exit(1)
    # file:///C:/name/nm0000701/?ref_=tt_cst_t_2
    # url = sys.argv[1]
    url = "https://www.imdb.com/name/nm0000138/"
    output_dir = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else "movies"
    # Default to visible mode (headless=False) so user can see what's happening
    headless = '--headless' in sys.argv
    
    try:
        download_imdb_actor(url, output_dir, headless=headless)
        print("\nDownload completed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

