from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from deep_translator import GoogleTranslator
from collections import Counter
import requests
import re
import time
import os
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import concurrent.futures # Import for parallel execution

# BrowserStack credentials (ensure these are correctly set)
USERNAME = os.getenv("USERNAME")
ACCESS_KEY = os.getenv("ACCESS_KEY")

# Directory for saving images
IMAGE_SAVE_DIR = "downloaded_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# Helper function to handle cookie consent
def accept_cookie_consent(driver, session_name, timeout=15):
    try:
        print(f"[{session_name}] Looking for cookie consent...")
        cookie_dialog_container = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(@id, 'didomi-host') or contains(@class, 'didomi-popup') or contains(@class, 'consent-modal')]"))
        )
        print(f"[{session_name}] Cookie consent container found. Trying to find accept button...")
        
        accept_button = WebDriverWait(cookie_dialog_container, 5).until(
            EC.element_to_be_clickable((By.XPATH, 
                ".//button[contains(., 'Aceptar') or contains(., 'Accept') or contains(@aria-label, 'Accept') or contains(@data-cc-action, 'accept')] | "
                ".//a[contains(., 'Aceptar') or contains(., 'Accept')]"
            ))
        )
        accept_button.click()
        print(f"[{session_name}] Accepted cookie consent.")
        WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.XPATH, "//*[contains(@id, 'didomi-host') or contains(@class, 'didomi-popup') or contains(@class, 'consent-modal')]")))
        print(f"[{session_name}] Cookie consent disappeared.")
        return True
    except TimeoutException:
        print(f"[{session_name}] Timeout waiting for cookie consent to appear or button to be clickable within {timeout} seconds.")
    except NoSuchElementException:
        print(f"[{session_name}] Cookie consent button not found after dialog container was present. The locator might need adjustment.")
    except Exception as e:
        print(f"[{session_name}] An unexpected error occurred with cookie consent: {e}")
    return False


def scrape_opinion_translate_titles(bstack_caps):
    session_name = bstack_caps.get('sessionName', 'Unnamed Session')
    print(f"\n--- Starting test on {session_name} ---")

    options = webdriver.ChromeOptions() 
    options.set_capability('bstack:options', bstack_caps)

    driver = None
    titles = []
    translated_titles = []
    
    try:
        driver = webdriver.Remote(
            command_executor=f'https://{USERNAME}:{ACCESS_KEY}@hub-cloud.browserstack.com/wd/hub',
            options=options
        )
        print(f"[{session_name}] WebDriver initialized on BrowserStack.")

        driver.get("https://elpais.com/opinion/")
        print(f"[{session_name}] Navigated to El País Opinion section.")
        
        # Handle cookie consent specifically for the Opinion page, passing session_name
        accept_cookie_consent(driver, session_name)

        # Wait for article elements to be present and identify the first 5 unique articles
        article_elements_on_page = WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.XPATH, 
                "//article[.//h2/a[contains(@href, '/opinion/202')] or .//h3/a[contains(@href, '/opinion/202')]]"
            ))
        )
        
        print(f"[{session_name}] Found {len(article_elements_on_page)} potential article elements with specific links on Opinion page.")
        
        articles_to_process = []
        processed_urls_set = set() # To store URLs already added to avoid duplicates

        # Filter for unique and valid links from the first 5 found articles
        for idx, article_elem in enumerate(article_elements_on_page):
            if len(articles_to_process) >= 5:
                break # Stop after finding 5 articles

            article_url = None
            try:
                link_element = None
                try:
                    link_element = article_elem.find_element(By.XPATH, ".//h2/a[contains(@href, '/opinion/202')]")
                except NoSuchElementException:
                    try:
                        link_element = article_elem.find_element(By.XPATH, ".//h3/a[contains(@href, '/opinion/202')]")
                    except NoSuchElementException:
                        link_element = article_elem.find_element(By.XPATH, ".//a[starts-with(@href, 'https://elpais.com/opinion/202')]")
                
                if link_element:
                    url = link_element.get_attribute("href")
                    if url and "elpais.com/opinion/202" in url and url not in processed_urls_set:
                        article_url = url
                        
            except Exception as e:
                print(f"[{session_name}] Could not extract valid article link from element {idx}: {e}")
                pass # Continue to next element if link extraction fails

            if article_url:
                articles_to_process.append({"element": article_elem, "url": article_url})
                processed_urls_set.add(article_url)


        if not articles_to_process:
            print(f"[{session_name}] No valid specific article links found to process on the Opinion page based on current criteria.")
            return [] # Return empty list if no articles found

        print(f"[{session_name}] Proceeding to scrape details for {len(articles_to_process)} unique articles...")

        for i, article_info in enumerate(articles_to_process):
            current_article_url = article_info['url']
            
            print(f"[{session_name}] --- Processing Article {i+1} of {len(articles_to_process)} ---")
            print(f"[{session_name}] Navigating to: {current_article_url}")
            driver.get(current_article_url)
            
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, 'h1'))
            )
            time.sleep(1)

            # Get Title
            title = "Title Not Found"
            try:
                title_elem = driver.find_element(By.TAG_NAME, "h1")
                title = title_elem.text.strip()
                
                if not title:
                    try:
                        title_elem_fallback = driver.find_element(By.CSS_SELECTOR, "h2.c_t, .article-header h2, .article-main-title")
                        title = title_elem_fallback.text.strip()
                    except NoSuchElementException:
                        pass
                
                if title:
                    titles.append(title)
                    print(f"[{session_name}] Original Title: {title}")
                else:
                    print(f"[{session_name}] Title element found but text is empty for {current_article_url}")

            except (NoSuchElementException, TimeoutException) as e:
                print(f"[{session_name}] Title (H1 or H2/CSS fallback) not found for {current_article_url}: {e}")
            except Exception as e:
                print(f"[{session_name}] An unexpected error getting title for {current_article_url}: {e}")

            # Get Content - REFINED LOGIC
            article_content_text = "Content Not Found"
            try:
                content_elements = WebDriverWait(driver, 20).until(
                    EC.presence_of_all_elements_located((By.XPATH, 
                        "//div[contains(@class, 'a_c') and @data-dtm-region='articulo_cuerpo']//p[string-length(normalize-space()) > 5] | "
                        "//div[@id='cuerpo_noticia']//p[string-length(normalize-space()) > 5] | "
                        "//div[contains(@class, 'article_body')]//p[string-length(normalize-space()) > 5] | "
                        "//div[contains(@class, 'c-content')]//p[string-length(normalize-space()) > 5] | "
                        "//div[contains(@class, 'article-text')]//p[string-length(normalize-space()) > 5] | "
                        "//article//p[string-length(normalize-space()) > 5]"
                    ))
                )
                
                if content_elements:
                    article_content_text = "\n".join([p.text.strip() for p in content_elements if p.text.strip()])
                    print(f"[{session_name}] Content (first 500 chars):")
                    print(article_content_text[:500] + "..." if len(article_content_text) > 500 else article_content_text)
                else:
                    print(f"[{session_name}] No substantial paragraphs found within common content containers for this article after all attempts.")

            except TimeoutException:
                print(f"[{session_name}] Timeout waiting for content paragraphs for {current_article_url}.")
            except StaleElementReferenceException:
                print(f"[{session_name}] Stale element reference when trying to get content for {current_article_url}.")
            except Exception as e:
                print(f"[{session_name}] Error scraping content for {current_article_url}: {e}")

            # Translate Title
            translated = "Translation Failed"
            if title != "Title Not Found" and title:
                try:
                    translated = GoogleTranslator(source='auto', target='en').translate(title)
                    translated_titles.append(translated)
                    print(f"[{session_name}] Translated Title: {translated}")
                except Exception as e:
                    print(f"[{session_name}] Translation failed for '{title}': {e}")
            else:
                print(f"[{session_name}] Skipping translation as title was not found or was empty.")

            # Download Cover Image - REFINED LOGIC
            try:
                img_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, 
                        "//figure[contains(@class, 'a_m')]//img[@src] | "
                        "//figure[contains(@class, 'c-figure')]//img[@src] | "
                        "//div[contains(@class, 'article-media')]//img[@src] | "
                        "//img[contains(@class, 'c_m_e') and @src] | "
                        "//picture//img[@src] | "
                        "//meta[@property='og:image' and @content]"
                    ))
                )
                
                img_url = img_element.get_attribute("src")
                if not img_url and img_element.tag_name == 'meta' and img_element.get_attribute('property') == 'og:image':
                    img_url = img_element.get_attribute('content')

                if img_url:
                    if not img_url.startswith('http'):
                        print(f"[{session_name}] Warning: Image URL is relative or invalid: {img_url}. Skipping download.")
                        img_url = None
                    
                    if img_url:
                        base_filename = os.path.basename(img_url).split('?')[0].split('#')[0]
                        if '.' not in base_filename:
                            base_filename += '.jpg' 
                        
                        filename = f"article_{i+1}_{session_name.replace(' ', '_')}_{base_filename}" # Unique filename per session
                        full_path = os.path.join(IMAGE_SAVE_DIR, filename)

                        try:
                            response = requests.get(img_url, stream=True, timeout=10)
                            response.raise_for_status()
                            with open(full_path, "wb") as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            print(f"[{session_name}] Downloaded image: {full_path}")
                        except requests.exceptions.RequestException as req_err:
                            print(f"[{session_name}] Error downloading image {img_url}: {req_err}")
                else:
                    print(f"[{session_name}] No 'src' attribute found for cover image even if element located or URL was invalid.")
            except (NoSuchElementException, TimeoutException) as e:
                print(f"[{session_name}] No cover image element found or timed out for Article {i+1}: {e}")
            except Exception as e:
                print(f"[{session_name}] An unexpected error finding/downloading image for Article {i+1}: {e}")

            driver.back()
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.XPATH, 
                    "//article[.//h2/a[contains(@href, '/opinion/202')] or .//h3/a[contains(@href, '/opinion/202')]]"
                ))
            )

    except Exception as e:
        print(f"[{session_name}] An unexpected error occurred during BrowserStack scraping: {e}")
        if driver:
            driver.execute_script('browserstack_executor: {"action": "setSessionStatus", "arguments": {"status":"failed", "reason": "%s"}}' % str(e))
    finally:
        if driver:
            driver.quit()
            print(f"[{session_name}] WebDriver closed.")
    return translated_titles

# Main execution block for parallel testing
if __name__ == "__main__":
    # Define capabilities for 5 parallel tests (combination of desktop and mobile)
    bstack_capabilities_list = [
        # Desktop 1: Windows 10, Chrome latest
        {
            "os": "Windows",
            "osVersion": "10",
            "browserName": "Chrome",
            "browserVersion": "latest",
            "sessionName": "Win10 Chrome Test",
            "buildName": "El Pais Parallel Scrape",
            "debug": "true",
            "networkLogs": "true",
            "consoleLogs": "debug",
            "seleniumVersion": "4.0.0" 
        },
        # Desktop 2: macOS Sonoma, Safari latest
        {
            "os": "OS X",
            "osVersion": "Sonoma", 
            "browserName": "Safari", 
            "browserVersion": "latest",
            "sessionName": "Mac Sonoma Safari Test", 
            "buildName": "El Pais Parallel Scrape",
            "debug": "true",
            "networkLogs": "true",
            "consoleLogs": "debug",
            "seleniumVersion": "4.0.0"
        },
        # Desktop 3: Windows 11, Edge latest
        {
            "os": "Windows",
            "osVersion": "11",
            "browserName": "Edge",
            "browserVersion": "latest",
            "sessionName": "Win11 Edge Test",
            "buildName": "El Pais Parallel Scrape",
            "debug": "true",
            "networkLogs": "true",
            "consoleLogs": "debug",
            "seleniumVersion": "4.0.0"
        },
        # Mobile 1: Android (e.g., Samsung Galaxy S23, Chrome) - Real device
        {
            "deviceName": "Samsung Galaxy S23",
            "osVersion": "13.0", 
            "browserName": "Chrome",
            "realMobile": "true",
            "sessionName": "Android S23 Chrome Test",
            "buildName": "El Pais Parallel Scrape",
            "debug": "true",
            "networkLogs": "true",
            "consoleLogs": "debug",
            "seleniumVersion": "4.0.0"
        },
        # Mobile 2: iOS (e.g., iPhone 14 Pro, Safari) - Real device
        {
            "deviceName": "iPhone 14 Pro",
            "osVersion": "16", # iOS 16
            "browserName": "Safari",
            "realMobile": "true", 
            "sessionName": "iPhone 14 Pro Safari Test",
            "buildName": "El Pais Parallel Scrape",
            "debug": "true",
            "networkLogs": "true",
            "consoleLogs": "debug",
            "seleniumVersion": "4.0.0"
        }
    ]

    all_translated_titles = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_caps = {executor.submit(scrape_opinion_translate_titles, caps): caps for caps in bstack_capabilities_list}

        for future in concurrent.futures.as_completed(future_to_caps):
            caps = future_to_caps[future]
            session_name = caps.get('sessionName', 'Unnamed Session')
            try:
                translated_titles_from_thread = future.result() 
                if translated_titles_from_thread:
                    all_translated_titles.extend(translated_titles_from_thread)
            except Exception as exc:
                print(f'[{session_name}] Test generated an exception: {exc}')
    
    print("\n--- Consolidated Analysis of All Translated Titles ---")
    words = []
    for title in all_translated_titles:
        words.extend(re.findall(r'\b\w+\b', title.lower()))

    word_freq = Counter(words)
    
    # Print words that appear more than twice (i.e., frequency > 2)
    print("Words repeated more than twice (3 or more times):")
    found_repeated_words = False
    for word, freq in word_freq.items():
        if freq > 2: 
            print(f"'{word}': {freq} times")
            found_repeated_words = True
    
    if not found_repeated_words:
        print("No words were repeated more than twice across all translated headers.")