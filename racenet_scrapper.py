from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import json
import re
import time
import logging
import warnings
import os
import requests
from datetime import datetime, timezone

if os.path.exists('.env'):
    from dotenv import load_dotenv
    load_dotenv()

BASE_API = 'https://api.p.racingwa.com.au'


def search_active_horse(name):
    res = requests.get(f'{BASE_API}/horses/search?name={requests.utils.quote(name)}', timeout=10)
    if not res.ok:
        return None
    results = res.json()
    return next((h for h in results if h.get('horseStatus') == 'active'), None)


def fetch_profile(horse_id):
    res = requests.get(f'{BASE_API}/horses/{horse_id}/profile', timeout=10)
    return res.json() if res.ok else None


def fetch_races(horse_id):
    to_date = datetime.now().strftime('%Y-%m-%d')
    res = requests.get(f'{BASE_API}/horses/{horse_id}/races?fromDate=2006-01-01&toDate={to_date}', timeout=10)
    return res.json() if res.ok else []


def empty_bucket():
    return {'s': 0, 'w': 0, 'p2': 0, 'p3': 0}


def fmt(b):
    return f"{b['s']}:{b['w']}-{b['p2']}-{b['p3']}"


def get_season_start():
    now = datetime.now()
    year = now.year if now.month >= 8 else now.year - 1
    return datetime(year, 8, 1)


def compute_stats(races):
    actual = [r for r in races if not r.get('isTrial')]
    season_start = get_season_start()
    season_label = f"Season Stats ({season_start.year}/{season_start.year + 1})"

    def tally(subset):
        overview = empty_bucket()
        buckets = {k: empty_bucket() for k in ['firm', 'good', 'soft', 'heavy']}
        up_buckets = {}
        last_date = None
        up_count = 0

        sorted_races = sorted(subset, key=lambda r: r.get('meetingDate', ''))

        for race in sorted_races:
            try:
                pos = int(race.get('finishedPosition', ''))
            except (ValueError, TypeError):
                continue

            if last_date:
                gap = (datetime.strptime(race['meetingDate'], '%Y-%m-%d') - datetime.strptime(last_date, '%Y-%m-%d')).days
                if gap > 60:
                    up_count = 0
            up_count += 1
            last_date = race.get('meetingDate')

            up_key = '1stUp' if up_count == 1 else ('2ndUp' if up_count == 2 else None)
            if up_key:
                if up_key not in up_buckets:
                    up_buckets[up_key] = empty_bucket()
                up_buckets[up_key]['s'] += 1
                if pos == 1: up_buckets[up_key]['w'] += 1
                if pos == 2: up_buckets[up_key]['p2'] += 1
                if pos == 3: up_buckets[up_key]['p3'] += 1

            overview['s'] += 1
            if pos == 1: overview['w'] += 1
            if pos == 2: overview['p2'] += 1
            if pos == 3: overview['p3'] += 1

            cond = (race.get('trackCondition') or '').lower()
            cond_key = 'firm' if cond.startswith('f') else 'good' if cond.startswith('g') else 'soft' if cond.startswith('s') else 'heavy' if cond.startswith('h') else None
            if cond_key:
                buckets[cond_key]['s'] += 1
                if pos == 1: buckets[cond_key]['w'] += 1
                if pos == 2: buckets[cond_key]['p2'] += 1
                if pos == 3: buckets[cond_key]['p3'] += 1

        return {
            'overview': fmt(overview),
            '1stUp': fmt(up_buckets.get('1stUp', empty_bucket())),
            '2ndUp': fmt(up_buckets.get('2ndUp', empty_bucket())),
            'firm': fmt(buckets['firm']),
            'good': fmt(buckets['good']),
            'soft': fmt(buckets['soft']),
            'heavy': fmt(buckets['heavy']),
        }

    season_races = [r for r in actual if r.get('meetingDate', '') >= season_start.strftime('%Y-%m-%d')]

    return [
        {'title': season_label, 'stats': tally(season_races)},
        {'title': 'Career Form', 'stats': tally(actual)},
    ]


def fetch_horse_names():
    url = os.getenv('NEXTJS_BASE_URL', '').rstrip('/')
    try:
        res = requests.get(f'{url}/api/horses', timeout=10)
        if res.ok:
            horses = res.json()
            return [h['title'] for h in horses if h.get('title')]
        print(f'⚠ Failed to fetch horses: {res.status_code}')
    except Exception as e:
        print(f'⚠ Error fetching horses: {e}')
    return []


def scrape_horse_profiles(horse_names):
    profiles = {}
    errors = []
    for name in horse_names:
        print(f'Scraping profile: {name}')
        try:
            match = search_active_horse(name)
            if not match:
                errors.append(f'{name}: no active horse found')
                time.sleep(1)
                continue
            horse_id = match['horseId']
            time.sleep(0.5)
            profile = fetch_profile(horse_id)
            races = fetch_races(horse_id)
            if profile:
                profiles[name] = {**profile, 'stats': compute_stats(races)}
                print(f'  ✓ {name}')
            else:
                errors.append(f'{name}: profile fetch failed')
        except Exception as e:
            errors.append(f'{name}: {e}')
        time.sleep(1.5)

    return {
        'profiles': profiles,
        'updatedAt': datetime.now(timezone.utc).isoformat(),
    }, errors



# Suppress unnecessary warnings
warnings.filterwarnings('ignore')
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


def parse_race_result(item):
    """Parse a single race result item"""
    race_data = {}

    # Extract position information
    position_div = item.find('div', class_='position')
    if position_div:
        finish_pos = position_div.find('div', class_='finish-position')
        race_data['position'] = finish_pos.text.strip() if finish_pos else None

        event_starters = position_div.find('div', class_='event-starters')
        race_data['starters'] = event_starters.text.strip() if event_starters else None

        margin_div = position_div.find('div', class_='margin')
        race_data['margin'] = margin_div.text.strip() if margin_div else None

    # Extract detail information
    detail_div = item.find('div', class_='detail')
    if detail_div:
        # Date
        date_div = detail_div.find('div', class_='date')
        race_data['date'] = date_div.text.strip() if date_div else None

        # Horse/Competitor name
        competitor_name = detail_div.find('div', class_='competitor-name')
        if competitor_name:
            horse_link = competitor_name.find('a')
            if horse_link:
                horse_name_text = horse_link.text.strip()
                # Remove the number in parentheses
                race_data['horse_name'] = re.sub(r'\s*\(\d+\)\s*$', '', horse_name_text).strip()
                race_data['horse_url'] = 'https://www.racenet.com.au' + horse_link.get('href', '') if horse_link.get(
                    'href') else None

        # Meeting name and race link
        meeting_name = detail_div.find('div', class_='meeting-name')
        if meeting_name:
            meeting_link = meeting_name.find('a')
            if meeting_link:
                race_data['meeting'] = meeting_link.text.strip()
                race_data['race_url'] = 'https://www.racenet.com.au' + meeting_link.get('href', '') if meeting_link.get(
                    'href') else None

        # Event name
        event_names = detail_div.find_all('div', class_='event-name')
        if event_names:
            race_data['event_name'] = event_names[0].text.strip() if len(event_names) > 0 else None
            race_data['race_class'] = event_names[1].text.strip() if len(event_names) > 1 else None

        # Race info (distance, track condition, jockey, etc.)
        info_div = detail_div.find('div', class_='info')
        if info_div:
            info_text = info_div.get_text(separator=' ', strip=True)
            race_data['race_info'] = info_text

            # Extract distance
            distance_match = re.search(r'(\d+)m', info_text)
            race_data['distance'] = distance_match.group(0) if distance_match else None

            # Extract track condition
            track_condition = info_div.find('span', class_='track-condition')
            race_data['track_condition'] = track_condition.text.strip() if track_condition else None

    return race_data


IS_LAMBDA = bool(os.getenv('AWS_LAMBDA_FUNCTION_NAME'))


def get_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-logging')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    if IS_LAMBDA:
        chrome_options.add_argument('--single-process')
        chrome_options.add_argument('--homedir=/tmp')
        chrome_options.add_argument('--disk-cache-dir=/tmp/cache')
        chrome_options.binary_location = '/opt/chrome/chrome'
        service = Service(executable_path='/opt/chromedriver')
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())

    service.log_path = '/dev/null'
    return webdriver.Chrome(service=service, options=chrome_options)


def scrape_trainer_upcoming_races(trainer_url):
    driver = None

    try:
        driver = get_chrome_driver()

        print(f"Loading page: {trainer_url}")
        driver.get(trainer_url)

        # Wait for the page to load
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'profile-upcoming-races')))
        time.sleep(2)

        # Click on the "Results" tab to load race results
        print("Clicking on 'Results' tab...")
        try:
            # Find all tabs
            tabs = driver.find_elements(By.CSS_SELECTOR, "a.tab")

            results_tab = None
            for tab in tabs:
                tab_text = tab.text.strip()
                if tab_text == 'Results':
                    results_tab = tab
                    break

            if results_tab:
                # Scroll the element into view
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", results_tab)
                time.sleep(1)

                # Use JavaScript click to avoid interception
                driver.execute_script("arguments[0].click();", results_tab)
                print("Results tab clicked successfully")

                # Wait for the results sections to load
                time.sleep(3)

                # Click "Display More" button to load all results
                print("Looking for 'Display More' button...")
                max_clicks = 10  # Limit to prevent infinite loop
                clicks = 0

                while clicks < max_clicks:
                    try:
                        # Find the Display More button
                        display_more_buttons = driver.find_elements(By.XPATH,
                                                                    "//button[contains(text(), 'Display More')]")

                        if display_more_buttons:
                            button = display_more_buttons[0]
                            # Check if button is visible and enabled
                            if button.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(0.5)
                                driver.execute_script("arguments[0].click();", button)
                                print(f"  Clicked 'Display More' button ({clicks + 1} times)")
                                clicks += 1
                                time.sleep(2)  # Wait for new content to load
                            else:
                                break
                        else:
                            break
                    except:
                        break

                if clicks > 0:
                    print(f"Loaded additional results by clicking 'Display More' {clicks} times")

                # Final scroll to ensure everything is loaded
                print("Final scroll to load all content...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            else:
                print("Warning: Could not find Results tab")

        except Exception as e:
            print(f"Warning: Error during tab click: {e}")

        # Get the page source after JavaScript has executed
        page_source = driver.page_source



        # Parse with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')

        # Extract trainer name from upcoming races section
        upcoming_races_section = soup.find('div', class_='profile-upcoming-races')
        trainer_name = "Unknown"
        if upcoming_races_section:
            title_elem = upcoming_races_section.find('h2', class_='profile-upcoming-races__title')
            trainer_name = title_elem.text.strip().replace(' Upcoming Races', '') if title_elem else "Unknown"

        # ===== UPCOMING RACES =====
        upcoming_races = []
        if upcoming_races_section:
            race_items = upcoming_races_section.find_all('a', class_='profile-upcoming-races-item')
            print(f"Found {len(race_items)} upcoming race items")

            for idx, item in enumerate(race_items, 1):
                race_data = {}

                # Extract race URL
                race_data['race_url'] = 'https://www.racenet.com.au' + item.get('href', '') if item.get(
                    'href') else None

                # Extract silk image
                silk_img = item.find('img', alt='silk')
                race_data['silk_url'] = silk_img.get('src') if silk_img else None

                # Extract horse name
                horse_link = item.find('a', href=re.compile(r'/profiles/horse/'))
                if horse_link:
                    horse_name_span = horse_link.find('span', class_='competitor-name')
                    race_data['horse_name'] = horse_name_span.text.strip() if horse_name_span else None
                    race_data['horse_profile_url'] = 'https://www.racenet.com.au' + horse_link.get('href',
                                                                                                   '') if horse_link.get(
                        'href') else None
                else:
                    race_data['horse_name'] = None
                    race_data['horse_profile_url'] = None

                # Extract race details (R5 Ascot (Wed 24 Dec 2025))
                race_details = item.find('small')
                if race_details:
                    race_data['race_details'] = race_details.text.strip()

                    # Parse race details
                    details_text = race_details.text.strip()
                    race_match = re.match(r'R(\d+)\s+(.+?)\s+\((.+?)\)', details_text)
                    if race_match:
                        race_data['race_number'] = race_match.group(1)
                        race_data['track'] = race_match.group(2)
                        race_data['date'] = race_match.group(3)
                else:
                    race_data['race_details'] = None

                # Extract jockey information
                jockey_details = item.find('div', class_='horseracing-selection-details-name-details')
                if jockey_details:
                    jockey_link = jockey_details.find('a')
                    if jockey_link:
                        jockey_text = jockey_link.text.strip()
                        # Extract weight
                        weight_match = re.search(r'\((\d+(?:\.\d+)?kg)\)', jockey_text)
                        race_data['jockey_weight'] = weight_match.group(1) if weight_match else None
                        # Extract name (everything before the weight)
                        if weight_match:
                            race_data['jockey_name'] = jockey_text[:weight_match.start()].strip()
                        else:
                            race_data['jockey_name'] = jockey_text
                    else:
                        race_data['jockey_name'] = None
                        race_data['jockey_weight'] = None
                else:
                    race_data['jockey_name'] = None
                    race_data['jockey_weight'] = None

                upcoming_races.append(race_data)

        # ===== MAJOR WINS =====
        major_wins = []

        # Find major wins section using exact class name
        major_wins_section = soup.find('div', class_='profile-result-tab-list-desktop major-win')

        if major_wins_section:
            race_items = major_wins_section.find_all('div', class_='profile-result-tab-row-desktop')
            # Filter out hidden items (style="display: none;")
            visible_items = [item for item in race_items if item.get('style') != 'display: none;']
            print(f"Found {len(visible_items)} major win items")

            for item in visible_items:
                race_data = parse_race_result(item)
                major_wins.append(race_data)
        else:
            print("Warning: Major wins section not found")

        # ===== PREVIOUS RUNNERS =====
        previous_runners = []

        # Find previous runners section using exact class name
        previous_run_section = soup.find('div', class_='profile-result-tab-list-desktop previous-run')

        if previous_run_section:
            race_items = previous_run_section.find_all('div', class_='profile-result-tab-row-desktop')
            # Filter out hidden items (style="display: none;")
            visible_items = [item for item in race_items if item.get('style') != 'display: none;']
            print(f"Found {len(visible_items)} previous runner items")

            for item in visible_items:
                race_data = parse_race_result(item)
                previous_runners.append(race_data)
        else:
            print("Warning: Previous runners section not found")

        result = {
            "trainer_name": trainer_name,
            "trainer_url": trainer_url,
            "scrape_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "upcoming_races": {
                "total": len(upcoming_races),
                "races": upcoming_races
            },
            "major_wins": {
                "total": len(major_wins),
                "wins": major_wins
            },
            "previous_runners": {
                "total": len(previous_runners),
                "results": previous_runners
            }
        }

        return result

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        if driver:
            driver.quit()


def push_to_nextjs(data, path):
    url = os.getenv('NEXTJS_BASE_URL', '').rstrip('/')
    secret = os.getenv('SCRAPER_TOKEN')
    if not url or not secret:
        print("⚠ NEXTJS_BASE_URL or SCRAPER_TOKEN not set, skipping push")
        return
    try:
        res = requests.post(f'{url}{path}', json=data, headers={'Authorization': f'Bearer {secret}'}, timeout=30)
        if res.ok:
            print(f"✓ Pushed to {path}: {res.status_code}")
        else:
            print(f"✗ Push failed {path}: {res.status_code} {res.text}")
    except Exception as e:
        print(f"✗ Push error {path}: {e}")


def lambda_handler(event, context):
    trainer_url = "https://www.racenet.com.au/profiles/trainer/stefan-vahala"

    data = scrape_trainer_upcoming_races(trainer_url)
    if data:
        push_to_nextjs(data, '/api/trainer-data')
    else:
        print("Failed to scrape trainer data")

    horse_names = fetch_horse_names()
    if horse_names:
        profiles_data, errors = scrape_horse_profiles(horse_names)
        if errors:
            print(f"Errors: {errors}")
        push_to_nextjs(profiles_data, '/api/scrape-profiles')
    else:
        print("No horses found, skipping profile scrape")

    return {'statusCode': 200, 'body': 'Scrape complete'}


if __name__ == '__main__':
    lambda_handler({}, {})