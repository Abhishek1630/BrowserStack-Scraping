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

# BrowserStack credentials
USERNAME = os.getenv("USERNAME")
ACCESS_KEY = os.getenv("ACCESS_KEY")
# Directory for saving images
IMAGE_SAVE_DIR = "downloaded_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# Helper function to handle cookie consent
def accept_cookie_consent(driver, timeout=15):
    try:
        print("Looking for cookie consent...")
        cookie_dialog_container = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(@id, 'didomi-host') or contains(@class, 'didomi-popup') or contains(@class, 'consent-modal')]"))
        )
        print("Cookie consent container found. Trying to find accept button...")
        
        accept_button = WebDriverWait(cookie_dialog_container, 5).until(
            EC.element_to_be_clickable((By.XPATH, 
                ".//button[contains(., 'Aceptar') or contains(., 'Accept') or contains(@aria-label, 'Accept') or contains(@data-cc-action, 'accept')] | "
                ".//a[contains(., 'Aceptar') or contains(., 'Accept')]"
            ))
        )
        accept_button.click()
        print("Accepted cookie consent.")
        WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.XPATH, "//*[contains(@id, 'didomi-host') or contains(@class, 'didomi-popup') or contains(@class, 'consent-modal')]")))
        print("Cookie consent disappeared.")
        return True
    except TimeoutException:
        print(f"Timeout waiting for cookie consent to appear or button to be clickable within {timeout} seconds.")
    except NoSuchElementException:
        print("Cookie consent button not found after dialog container was present. The locator might need adjustment.")
    except Exception as e:
        print(f"An unexpected error occurred with cookie consent: {e}")
    return False

# Function to scrape Opinion section using BrowserStack and analyze titles
def scrape_opinion_translate_titles():
    print("\n--- Opinion Article Titles (Translated) ---")
    # BrowserStack options
    bstack_options = {
        "os": "Windows",
        "osVersion": "10",
        "browserName": "Chrome",
        "browserVersion": "latest",
        "sessionName": "El Pais Opinion Scraper - Final Content Fix", # Updated session name
        "buildName": "El Pais Opinion Scraper with Article Tag Focus - Final Content Fix", # Updated build name
        "debug": "true",
        "networkLogs": "true",
        "consoleLogs": "debug",
    }

    options = webdriver.ChromeOptions()
    options.set_capability('bstack:options', bstack_options)

    driver = None
    titles = []
    translated_titles = []
    
    try:
        driver = webdriver.Remote(
            command_executor=f'https://{USERNAME}:{ACCESS_KEY}@hub-cloud.browserstack.com/wd/hub',
            options=options
        )
        print("WebDriver initialized on BrowserStack.")

        driver.get("https://elpais.com/opinion/")
        print("Navigated to El País Opinion section.")
        
        # Handle cookie consent specifically for the Opinion page
        accept_cookie_consent(driver)

        article_elements_on_page = WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.XPATH, 
                "//article[.//h2/a[contains(@href, '/opinion/202')] or .//h3/a[contains(@href, '/opinion/202')]]"
            ))
        )
        
        print(f"Found {len(article_elements_on_page)} potential article elements with specific links on Opinion page.")
        
        articles_to_process = []
        processed_urls_set = set() # To store URLs already added to avoid duplicates

        # Filter for unique and valid links from the first 5 found articles
        for idx, article_elem in enumerate(article_elements_on_page):
            if len(articles_to_process) >= 5:
                break # Stop after finding 5 articles

            article_url = None
            try:
                # Prioritize links within h2, then h3 that contain the year pattern
                link_element = None
                try:
                    link_element = article_elem.find_element(By.XPATH, ".//h2/a[contains(@href, '/opinion/202')]")
                except NoSuchElementException:
                    try:
                        link_element = article_elem.find_element(By.XPATH, ".//h3/a[contains(@href, '/opinion/202')]")
                    except NoSuchElementException:
                        # Fallback: find any link within the article that looks like a full article URL
                        link_element = article_elem.find_element(By.XPATH, ".//a[starts-with(@href, 'https://elpais.com/opinion/202')]")
                
                if link_element:
                    url = link_element.get_attribute("href")
                    # Further validate URL to ensure it's a specific article and not just a section
                    if url and "elpais.com/opinion/202" in url and url not in processed_urls_set:
                        article_url = url
                        
            except Exception as e:
                print(f"Could not extract valid article link from element {idx}: {e}") # Debugging link extraction
                pass # Continue to next element if link extraction fails

            if article_url:
                articles_to_process.append({"element": article_elem, "url": article_url})
                processed_urls_set.add(article_url)


        if not articles_to_process:
            print("No valid specific article links found to process on the Opinion page based on current criteria.")
            return

        print(f"Proceeding to scrape details for {len(articles_to_process)} unique articles...")

        for i, article_info in enumerate(articles_to_process):
            current_article_url = article_info['url']
            
            print(f"\n--- Processing Article {i+1} of {len(articles_to_process)} ---")
            print(f"Navigating to: {current_article_url}")
            driver.get(current_article_url)
            
            # Wait for the article's main content to load (e.g., the main title H1)
            # Increased timeout for a robust wait
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, 'h1'))
            )
            time.sleep(1) # Small pause to allow dynamic content to fully render after navigation

            # Get Title
            title = "Title Not Found" # Default
            try:
                # Try H1 first
                title_elem = driver.find_element(By.TAG_NAME, "h1")
                title = title_elem.text.strip()
                
                # If H1 is empty, try common H2/div selectors
                if not title:
                    try:
                        title_elem_fallback = driver.find_element(By.CSS_SELECTOR, "h2.c_t, .article-header h2, .article-main-title")
                        title = title_elem_fallback.text.strip()
                    except NoSuchElementException:
                        pass # No fallback title found
                
                if title:
                    titles.append(title)
                    print(f"Original Title: {title}")
                else:
                    print(f"Title element found but text is empty for {current_article_url}")

            except (NoSuchElementException, TimeoutException) as e:
                print(f"Title (H1 or H2/CSS fallback) not found for {current_article_url}: {e}")
            except Exception as e:
                print(f"An unexpected error getting title for {current_article_url}: {e}")


            # Get Content - REFINED LOGIC HERE based on provided HTML
            article_content_text = "Content Not Found"
            try:
                # Priority 1: Main article body div by ID or common class, INCLUDING the one from your HTML
                content_elements = WebDriverWait(driver, 20).until( # Increased timeout for robustness
                    EC.presence_of_all_elements_located((By.XPATH, 
                        "//div[contains(@class, 'a_c') and @data-dtm-region='articulo_cuerpo']//p[string-length(normalize-space()) > 5] | " # NEW, specific for the provided HTML
                        "//div[@id='cuerpo_noticia']//p[string-length(normalize-space()) > 5] | " # Keep as fallback for other articles
                        "//div[contains(@class, 'article_body')]//p[string-length(normalize-space()) > 5] | " # Keep as fallback
                        "//div[contains(@class, 'c-content')]//p[string-length(normalize-space()) > 5] | " # Keep as fallback
                        "//div[contains(@class, 'article-text')]//p[string-length(normalize-space()) > 5] | " # Keep as fallback
                        "//article//p[string-length(normalize-space()) > 5]" # General article paragraphs - lowest priority fallback
                    ))
                )
                
                if content_elements:
                    article_content_text = "\n".join([p.text.strip() for p in content_elements if p.text.strip()])
                    print("Full Article Content:")
                    print(article_content_text)
                else:
                    print("No substantial paragraphs found within common content containers for this article after all attempts.")

            except TimeoutException:
                print(f"Timeout waiting for content paragraphs for {current_article_url}.")
            except StaleElementReferenceException:
                print(f"Stale element reference when trying to get content for {current_article_url}. This might resolve on next run due to improved waits/selectors.")
            except Exception as e:
                print(f"Error scraping content for {current_article_url}: {e}")

            # Translate Title - No change needed, already working
            translated = "Translation Failed"
            if title != "Title Not Found" and title: # Ensure title is not empty string
                try:
                    translated = GoogleTranslator(source='auto', target='en').translate(title)
                    translated_titles.append(translated)
                    print(f"Translated Title: {translated}")
                except Exception as e:
                    print(f"Translation failed for '{title}': {e}")
            else:
                print("Skipping translation as title was not found or was empty.")

            # Download Cover Image - REFINED LOGIC HERE based on provided HTML
            try:
                # Look for common image elements within the article (e.g., in a figure or directly)
                img_element = WebDriverWait(driver, 15).until( # Increased wait time
                    EC.presence_of_element_located((By.XPATH, 
                        "//figure[contains(@class, 'a_m')]//img[@src] | " # NEW: Specific for the provided HTML
                        "//figure[contains(@class, 'c-figure')]//img[@src] | "
                        "//div[contains(@class, 'article-media')]//img[@src] | "
                        "//img[contains(@class, 'c_m_e') and @src] | "
                        "//picture//img[@src] | "
                        "//meta[@property='og:image' and @content]" # Fallback to Open Graph image if visible
                    ))
                )
                
                img_url = img_element.get_attribute("src")
                if not img_url and img_element.tag_name == 'meta' and img_element.get_attribute('property') == 'og:image':
                    img_url = img_element.get_attribute('content') # Get content from meta tag

                if img_url:
                    # Ensure it's a valid HTTP/HTTPS URL
                    if not img_url.startswith('http'):
                        print(f"Warning: Image URL is relative or invalid: {img_url}. Skipping download.")
                        img_url = None # Set to None to prevent download attempt
                    
                    if img_url:
                        # Clean URL to get a simple filename
                        base_filename = os.path.basename(img_url).split('?')[0].split('#')[0]
                        # Ensure filename has an extension, default to .jpg if not clear
                        if '.' not in base_filename:
                            base_filename += '.jpg' 
                        
                        filename = f"article_{i+1}_{base_filename}"
                        full_path = os.path.join(IMAGE_SAVE_DIR, filename)

                        try:
                            response = requests.get(img_url, stream=True, timeout=10) # Added timeout for requests
                            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                            with open(full_path, "wb") as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            print(f"Downloaded image: {full_path}")
                        except requests.exceptions.RequestException as req_err:
                            print(f"Error downloading image {img_url}: {req_err}")
                else:
                    print("No 'src' attribute found for cover image even if element located or URL was invalid.")
            except (NoSuchElementException, TimeoutException) as e:
                print(f"No cover image element found or timed out for Article {i+1}: {e}")
            except Exception as e:
                print(f"An unexpected error finding/downloading image for Article {i+1}: {e}")

            # Go back to the Opinion section page for the next article
            driver.back()
            # Wait for the article list to be visible again using the same robust XPath
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.XPATH, 
                    "//article[.//h2/a[contains(@href, '/opinion/202')] or .//h3/a[contains(@href, '/opinion/202')]]"
                ))
            )

    except Exception as e:
        print(f"An unexpected error occurred during BrowserStack scraping: {e}")
    finally:
        if driver:
            driver.quit()
            print("WebDriver closed.")

    # Analyze repeated words
    print("\n--- Repeated Words in Translated Titles ---")
    words = []
    for title in translated_titles:
        # Using re.findall to get all words, then convert to lowercase
        words.extend(re.findall(r'\b\w+\b', title.lower()))

    word_freq = Counter(words)
    # Print words that appear more than twice
    for word, freq in word_freq.items():
        if freq > 2: # Changed condition to 'more than twice' (i.e., 3 or more times)
            print(f"'{word}': {freq} times")
            
# Run only the Opinion section scraping
if __name__ == "__main__":
    scrape_opinion_translate_titles()