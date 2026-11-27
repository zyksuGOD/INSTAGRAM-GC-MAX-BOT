import os
import re
import time
import json
import threading
import http.cookiejar
from datetime import datetime
from flask import Flask
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, PleaseWaitFewMinutes

# ---------- CONFIG ----------
IG_USERNAME = os.getenv("IG_USERNAME", "iy7qt")
GROUP_THREAD_ID = os.getenv("GROUP_THREAD_ID", "1158412246605899")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "eren_ye4gerrr")
COOLDOWN_HOURS = int(os.getenv("WELCOME_COOLDOWN_HOURS", 6))

WELCOME_TEXT = os.getenv("WELCOME_TEXT", "WELCOME TO OUR GC @{user} HOW ARE YOU 💖🥰")
IGNORE_REPLY = os.getenv("IGNORE_REPLY", "AWW BACCHA ISSOKIEE MEIN HU NA APKE LIYE 🥹💋")
LINK_REPLY = os.getenv("LINK_REPLY", "AWW TERE B44P KI BIWI KI PICS SHARE KAR RHA HAI KYA GC PE 😍💦👅")
GOOD_MORNING_TEXT = os.getenv("GOOD_MORNING_TEXT", "GOOD MORNING GUYS ☀️💖")
GOOD_NIGHT_TEXT = os.getenv("GOOD_NIGHT_TEXT", "GOOD NIGHT GUYS 🌙💤")

# ---------- STATE ----------
STATE_FILE = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"welcomed": {}, "last_seen_msg": {}, "last_gm": "", "last_gn": ""}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

state = load_state()

# ---------- CLIENT ----------
cl = Client()

def load_cookies_netscape(path="cookies.txt"):
    jar = http.cookiejar.MozillaCookieJar(path)
    jar.load(ignore_discard=True, ignore_expires=True)

    cookies_dict = {}
    for cookie in jar:
        cookies_dict[cookie.name] = cookie.value

    cl.set_cookies(cookies_dict)

    user_id = cookies_dict.get("ds_user_id")
    if not user_id:
        raise SystemExit("[-] ds_user_id cookie missing")

    cl.user_id = user_id
    cl.username = IG_USERNAME

    try:
        info = cl.user_info(user_id)
        print(f"[+] Logged in as @{info.username} (pk={info.pk})")
        return True
    except Exception as e:
        print(f"[-] Cookie verify failed: {e}")
        return False

def init_client():
    if not load_cookies_netscape():
        raise SystemExit("Cookies invalid/expired — fresh cookies chahiye")

# ---------- HELPERS ----------
LINK_PATTERN = re.compile(
    r"(https?://)?(chat\.whatsapp\.com|instagram\.com|t\.me|discord\.gg|"
    r"chat\.instagram\.com|ig\.me)/\S+",
    re.IGNORECASE
)

def contains_gc_link(text):
    return bool(LINK_PATTERN.search(text or ""))

def should_welcome(user_id):
    now = time.time()
    last = state["welcomed"].get(user_id, 0)
    if now - last >= COOLDOWN_HOURS * 3600:
        state["welcomed"][user_id] = now
        save_state(state)
        return True
    return False

def get_gc_thread():
    try:
        t = cl.direct_thread(GROUP_THREAD_ID)
        print(f"[+] GC thread loaded: {t.id} ({t.thread_title})")
        return t
    except Exception as e:
        print(f"[-] Thread load fail: {e}")
        raise SystemExit("GROUP_THREAD_ID invalid ya access nahi hai")

# ---------- SEND ----------
def send_welcome(thread_id, user_id, username):
    if not should_welcome(user_id):
        return
    msg = WELCOME_TEXT.format(user=username)
    try:
        cl.direct_send(msg, thread_ids=[thread_id])
        print(f"[+] Welcomed @{username}")
    except Exception as e:
        print(f"[-] Welcome fail: {e}")

def send_reply(thread_id, reply_to_msg, text):
    try:
        cl.direct_send(text, thread_ids=[thread_id], reply_to_message=reply_to_msg)
        print(f"[+] Replied: {text[:40]}")
    except Exception as e:
        print(f"[-] Reply fail: {e}")

# ---------- POLL LOOP ----------
def poll_loop():
    thread = get_gc_thread()
    thread_id = thread.id
    print(f"[*] Polling GC {thread_id} every 3s")

    while True:
        try:
            t = cl.direct_thread(thread_id)
            messages = t.messages[:20]

            for m in reversed(messages):
                mid = m.id
                last_seen = state["last_seen_msg"].get(thread_id)

                if last_seen == mid:
                    break
                if str(m.user_id) == str(cl.user_id):
                    state["last_seen_msg"][thread_id] = mid
                    continue

                user_id = str(m.user_id)
                username = m.user.username if m.user else "user"
                text = m.text or ""

                # 1. NEW MEMBER
                if m.item_type == "action_log" and "joined" in text.lower():
                    send_welcome(thread_id, user_id, username)
                    state["last_seen_msg"][thread_id] = mid
                    save_state(state)
                    continue

                # 2. IGNORE TRIGGER
                if "ignore" in text.lower():
                    send_reply(thread_id, mid, IGNORE_REPLY)
                    state["last_seen_msg"][thread_id] = mid
                    save_state(state)
                    continue

                # 3. GC LINK
                if contains_gc_link(text):
                    send_reply(thread_id, mid, LINK_REPLY)
                    state["last_seen_msg"][thread_id] = mid
                    save_state(state)
                    continue

                state["last_seen_msg"][thread_id] = mid

            save_state(state)
            time.sleep(3)

        except PleaseWaitFewMinutes:
            print("[!] Rate limited. Wait 60s.")
            time.sleep(60)
        except LoginRequired:
            print("[!] Session expired. Re-login needed.")
            time.sleep(300)
        except Exception as e:
            print(f"[-] Poll error: {e}")
            time.sleep(5)

# ---------- DAILY SCHEDULER ----------
def daily_scheduler():
    thread = get_gc_thread()
    thread_id = thread.id
    while True:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        if now.hour == 0 and now.minute == 0 and state["last_gn"] != today:
            try:
                cl.direct_send(GOOD_NIGHT_TEXT, thread_ids=[thread_id])
                state["last_gn"] = today
                save_state(state)
                print("[+] Good night sent")
            except Exception as e:
                print(f"[-] GN fail: {e}")

        if now.hour == 7 and now.minute == 0 and state["last_gm"] != today:
            try:
                cl.direct_send(GOOD_MORNING_TEXT, thread_ids=[thread_id])
                state["last_gm"] = today
                save_state(state)
                print("[+] Good morning sent")
            except Exception as e:
                print(f"[-] GM fail: {e}")

        time.sleep(30)

# ---------- ADMIN DM RELAY ----------
def admin_relay_loop():
    try:
        admin_id = cl.user_id_from_username(ADMIN_USERNAME)
        print(f"[+] Admin resolved: @{ADMIN_USERNAME} (pk={admin_id})")
    except Exception as e:
        print(f"[!] Admin lookup fail: {e}")
        return

    thread = get_gc_thread()
    gc_id = thread.id
    last_dm_id = None

    while True:
        try:
            dm_thread = cl.direct_thread_by_participants([admin_id])
            msgs = cl.direct_messages(dm_thread.id, amount=10)

            for m in reversed(msgs):
                if m.id == last_dm_id:
                    continue
                if str(m.user_id) != str(admin_id):
                    continue

                text = m.text or ""
                if text.startswith("/send_gc "):
                    payload = text[len("/send_gc "):].strip()
                    if payload:
                        try:
                            cl.direct_send(payload, thread_ids=[gc_id])
                            print(f"[+] Admin relay: {payload[:40]}")
                        except Exception as e:
                            print(f"[-] Relay send fail: {e}")

                last_dm_id = m.id

            time.sleep(5)

        except Exception as e:
            print(f"[-] Admin relay error: {e}")
            time.sleep(15)

# ---------- FLASK KEEPALIVE ----------
app = Flask(__name__)

@app.route("/")
def home():
    return "IG GC Bot alive", 200

@app.route("/health")
def health():
    return {"status": "ok", "ts": time.time()}, 200

def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

# ---------- MAIN ----------
if __name__ == "__main__":
    print("[*] Booting IG GC Bot...")
    init_client()

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=daily_scheduler, daemon=True).start()
    threading.Thread(target=admin_relay_loop, daemon=True).start()

    poll_loop()