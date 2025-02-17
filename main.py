import json
import sqlite3
import hashlib

import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import time
import random
import re
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains


# Replace this with your specific room code
ROOM_CODE = "uexb"
URL = f"https://jklm.fun/{ROOM_CODE}"
Talk = False

# Database setup
DB_FILE = "challenge_data.db"

def remove_non_bmp(text):
    return re.sub(r'[^\u0000-\uFFFF]', '', text)

def initialize_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                hash TEXT PRIMARY KEY
            )
        """)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT,
                answer TEXT,
                FOREIGN KEY(hash) REFERENCES prompts(hash)
            )
        """)
    conn.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    AuthId TEXT PRIMARY KEY,
                    Username TEXT NOT NULL
                );
            ''')
    conn.execute('''
                CREATE TABLE IF NOT EXISTS game_performance (
                    AuthId TEXT,
                    challenge_id TEXT,
                    elapsed_time INTEGER,  -- milliseconds as an integer
                    FOREIGN KEY (AuthId) REFERENCES players (AuthId),
                    PRIMARY KEY (AuthId, challenge_id)
                );
            ''')
    conn.commit()
    conn.close()

def get_hash(prompt: str, image: str = "") -> str:
    combined = prompt + image
    return hashlib.sha1(combined.encode()).hexdigest()

def get_img():
    try:
        # print("boop")
        # print(driver.execute_script("return milestone.challenge.image.data;"))
        img = driver.execute_script("""try {
        let imgData = milestone?.challenge?.image?.data;
        if (!imgData) return null;  // Handle null case
        
        let uint8Array = new Uint8Array(imgData);
        let binaryString = Array.from(uint8Array, byte => String.fromCharCode(byte)).join("");
        return btoa(binaryString);  // Convert to Base64
    } catch (e) {
        return null;  // Handle errors gracefully
    }""")
        return img
    except selenium.common.exceptions.JavascriptException:
        return None

js = """const foundPlayers = Object.entries(milestone.playerStatesByPeerId)
    .filter(([peerId, state]) => state.hasFoundSource) // Filter players who have found the source
    .map(([peerId, state]) => {
        const player = playersByPeerId[peerId];
        if (!player) return null;

        return {
            username: player.profile.nickname,
            elapsedTime: state.elapsedTime,
            guess: state.guess,
            authId: player.profile.auth ? player.profile.auth.id : null
        };
    })
    .filter(player => player !== null); // Remove null values

return JSON.stringify(foundPlayers);"""

def execute_js():
    return driver.execute_script(js)

initialize_database()

# Start WebDriver
options = webdriver.ChromeOptions()
# options.add_argument("--headless")  # Run headless for better performance
# options.add_argument("--disable-gpu")
driver = webdriver.Chrome(options=options)
# name = ["mnemosyne", "selene", "hyperion", "asteria", "eudaimonia", "calliope", "calypso"]
name = ["rynana"]

def join_room(driver_name, username):
    time.sleep(5)
    driver_name.find_element(By.CSS_SELECTOR, "button.toggleMute").click()
    elem = driver_name.find_element(By.CSS_SELECTOR, "input.styled.nickname")
    elem.clear()
    elem.send_keys(username)
    driver_name.find_element(By.CSS_SELECTOR, "button.styled").click()

def get_element_text_or_none(element):
    try:
        return element.text if element.is_displayed() else None
    except StaleElementReferenceException:
        return None
    except:
        return None

def get_answer_or_none(element):
    try:
        text = element.get_attribute("innerText").strip() or None  # Return None if text is empty or whitespace
        if text:
            # Remove all non-alpha characters
            return re.sub(r'[^a-z0-9]', '', text)
        return None
    except Exception:
        return None

def get_element_style_or_none(element, style_property):
    try:
        if element.is_displayed():
            style = element.get_attribute("style")
            if style_property in style:
                return style.split(f"{style_property}: ")[1].split(";")[0]
    except StaleElementReferenceException:
        pass
    except:
        pass
    return None

def save_challenge(prompt: str, image: str = ""):
    hash_value = get_hash(prompt, image)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO prompts (hash) VALUES (?)", (hash_value,))
    conn.commit()
    conn.close()
    return hash_value

def save_solution(hash_value:str, answer: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    outpt = False
    cursor.execute("SELECT 1 FROM answers WHERE hash = ? AND answer = ?", (hash_value, answer))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO answers (hash, answer) VALUES (?, ?)", (hash_value, answer))
        conn.commit()
        outpt = True
    conn.close()
    return outpt
    
def insert_player(AId: str, UN: str):
    conn = sqlite3.connect(DB_FILE)
    # Check if the player already exists
    existing_player = conn.execute('''
                SELECT 1 FROM players WHERE AuthId = ?
            ''', (AId,)).fetchone()

    if not existing_player:
        # If not, insert the new player
        conn.execute('''
                    INSERT INTO players (AuthId, Username) 
                    VALUES (?, ?);
                ''', (AId, UN))
        conn.commit()
    
def insert_game_performance(AuthId: str, Username:str, challenge_id: str, elapsed_time: int):
    insert_player(AuthId, Username)
    conn = sqlite3.connect(DB_FILE)
    existing_time = conn.execute('''
            SELECT elapsed_time 
            FROM game_performance 
            WHERE AuthId = ? AND challenge_id = ?
        ''', (AuthId, challenge_id)).fetchone()

    if existing_time:
        # If a time exists, only update if the new time is faster
        if elapsed_time < existing_time[0]:
            with conn:
                conn.execute('''
                        UPDATE game_performance 
                        SET elapsed_time = ? 
                        WHERE AuthId = ? AND challenge_id = ?;
                    ''', (elapsed_time, AuthId, challenge_id))
    else:
        # If no time exists, insert the new time
        with conn:
            conn.execute('''
                    INSERT INTO game_performance (AuthId, challenge_id, elapsed_time) 
                    VALUES (?, ?, ?);
                ''', (AuthId, challenge_id, elapsed_time))
    conn.commit()
    
def get_top_fastest_for_challenge(challenge_id: str, limit: int = 10):
    conn = sqlite3.connect(DB_FILE)
    query = '''
        SELECT p.Username, gp.elapsed_time 
        FROM game_performance gp
        JOIN players p ON gp.AuthId = p.AuthId
        WHERE gp.challenge_id = ?
        ORDER BY gp.elapsed_time ASC
        LIMIT ?;
    '''
    cur = conn.cursor()
    cur.execute(query, (challenge_id, limit))
    return cur.fetchall()
    
def get_answers(hash_value :str) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT answer FROM answers WHERE hash = ?", (hash_value,))
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results

def clean_text(text):
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

def jump_to_chat():
    driver.switch_to.default_content()
    input_box = driver.find_element(By.CSS_SELECTOR, "div.input textarea")
    return input_box

def js_send(elem: WebElement, text: str):
    driver.execute_script("arguments[0].value = arguments[1];", elem, text)
    elem.send_keys(Keys.ENTER)

def send(element: WebElement, txt: str):
    text = txt.replace("\n", "\n")
    while text:
        if len(text) <= 300:
            js_send(element, text)
            break

        # Find the last newline before 300 chars
        split_index = text.rfind("\n", 0, 300)
        if split_index == -1:
            split_index = 300  # If no newline, split at 300 chars

        part, text = text[:split_index], text[split_index:].lstrip()
        js_send(element, text)

try:
    # Open the room URL
    driver.get(URL)

    join_room(driver, name[random.randint(0, len(name) - 1)])

    # Wait until the iframe loads
    try:
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "phoenix.jklm.fun/games/popsauce")]'))
        )
        serv = 0
        driver.switch_to.frame(iframe) # 
    except:
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//iframe[contains(@src, "falcon.jklm.fun/games/popsauce")]'))
        )
        serv = 1
        driver.switch_to.frame(iframe)

    # Continuously monitor changes to the challenge area
    last_prompt = None
    last_text = None
    last_image_url = None

    while True:
        try:
            
            # Wait for the challenge div to appear
            challenge_div = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.challenge"))
            )

            # Extract the prompt
            prompt_element = challenge_div.find_element(By.CSS_SELECTOR, "div.header span.prompt")
            prompt = get_element_text_or_none(prompt_element)

            # Extract the text
            text_element = challenge_div.find_element(By.CSS_SELECTOR, "div.textScroll")
            text = get_element_text_or_none(text_element)

            # Extract the image URL
            """image_element = challenge_div.find_element(By.CSS_SELECTOR, "div.image div.actual")
            image_url = get_element_style_or_none(image_element, "background-image")

            # Clean up the image URL if it's in the blob format
            # print(image_url)
            if image_url and image_url.startswith("url("):
                image_url = image_url[5:-2]"""
            image_url = get_img()

            # Print changes only if they occur and the element is visible
            if prompt != last_prompt or text != last_text or (image_url != last_image_url and image_url is not None):

                content = text if text else image_url if image_url else None

                if content:
                    challenge_id = save_challenge(prompt, content)
                    print(challenge_id)
                    # print(f"saved prompt: {prompt}")
                    if prompt != last_prompt or content != last_text:
                        print(f"New challenge added: Prompt: {prompt}, Content: ...")

                if prompt:
                    print(f"Prompt: {prompt}")
                if text:
                    print(f"Text: {text}")
                if image_url:
                    print(f"Image: {image_url[0:10]}...")
                elif not prompt and not text:
                    challenge_result = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.challengeResult"))
                    )
                    answer_element = challenge_result.find_element(By.CSS_SELECTOR, "div.resultBox div.value")
                    fallback_answer = get_element_text_or_none(answer_element)
                    player_answers = json.loads(execute_js())

                    if fallback_answer:
                        print(f"Answer: {fallback_answer}")
                        time.sleep(0.3)
                        scoreboard_entries = driver.find_elements(By.CSS_SELECTOR, "div.scoreboard.lower div.entry")
                        if challenge_id:
                            save_solution(challenge_id, fallback_answer)
                        learned = []
                        for player in player_answers:
                            username = remove_non_bmp(player["username"])
                            if not username: username = " "
                            elapsed_time = player["elapsedTime"] / 1000
                            guess = player["guess"]
                            auth = player["authId"]
                            if username and elapsed_time:
                                print(f"Username: {username}, Time: {elapsed_time}, Guess:{guess}")
                            if challenge_id and elapsed_time:

                                cleaned_guess = clean_text(guess) if guess else None
                                cleaned_answer = clean_text(fallback_answer)

                                if cleaned_guess and cleaned_guess != cleaned_answer.lower():
                                    if save_solution(challenge_id, cleaned_guess):
                                        if Talk:
                                            learned.append(cleaned_guess)
                                    
                                if auth:
                                    insert_game_performance(auth, username, challenge_id, elapsed_time)
                        
                        if Talk and learned != []:
                            send(jump_to_chat(), f'Solution(s) {", ".join(learned)} were unknown to me! Thank you for contributing!')
                            driver.switch_to.frame(iframe)
                            learned = []
                                    
                        all_answers = get_answers(challenge_id)
                        print(all_answers)
                        times = get_top_fastest_for_challenge(challenge_id, 3)
                        print(times)
                        if times:
                            times = '\n'.join([f"{remove_non_bmp(x[0])}: {x[1]} seconds" for x in times])
                        else:
                            times = "No saved times. (Times by non-connected players are not saved.)"
                        if all_answers:
                            msg = f"--\nAnswer: {all_answers[0]}\n{('Alt answers: ' + ', '.join(sorted(all_answers[1:], key=len)) if len(all_answers) >= 2 and all_answers[1] != '' else '')}"
                        else:
                            print("answers being weird pls fix")
                            
                        if Talk:
                            send(jump_to_chat(), msg)
                            send(jump_to_chat(), f"--\nBest Times:\n{times}")
                            driver.switch_to.frame(iframe)
                            

                # Update last seen values
                last_prompt = prompt
                last_text = text
                last_image_url = image_url

            # Poll every second
            time.sleep(1)

        except TimeoutException:
            print("Timeout while waiting for challenge div. Retrying...")
            driver.switch_to.frame(iframe)
        except StaleElementReferenceException:
            print("Stale element encountered. Retrying...")
        except selenium.common.exceptions.JavascriptException:
            print("JS Error: tried to convert undefined to object ( i think a player left mid-game or something ) :(")
            time.sleep(1)
        except Exception as e:
            print(f"An error occurred: {e}")

finally:
    driver.quit()
