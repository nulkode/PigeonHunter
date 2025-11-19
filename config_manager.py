import json
import getpass
import logging
from pathlib import Path
from appdirs import user_config_dir
from imap_client import ImapClient

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(user_config_dir("PigeonHunter"))
CONFIG_FILE = CONFIG_DIR / "config.json"

def get_config_file_path():
    logger.debug("Config file path requested: %s", CONFIG_FILE)
    return CONFIG_FILE

def save_config(config_data):
    try:
        logger.debug("Creating config directory if not exists: %s", CONFIG_DIR)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        logger.info("Configuration saved to %s", CONFIG_FILE)
    except Exception as e:
        logger.error("Error saving configuration: %s", e, exc_info=True)

def load_config():
    logger.debug("Attempting to load config from %s", CONFIG_FILE)
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        logger.info("Configuration loaded successfully.")
        return config
    except Exception as e:
        logger.error("Error loading configuration: %s", e, exc_info=True)
        return None

def run_first_time_setup():
    logger.info("--- Starting PigeonHunter First-Time Setup ---")
    config = {}
    
    print("\n1. IMAP Server Configuration")
    server = input("IMAP Server (e.g., imap.gmail.com): ")
    user = input("Email Address: ")
    password = getpass.getpass("Email Password (or App Password): ")
    
    logger.debug("Connecting to IMAP server to fetch folders...")
    temp_client = ImapClient(server, user, password)
    
    if not temp_client.connect():
        logger.error("Setup failed: Could not connect to IMAP.")
        print("Failed to connect. Please check credentials and server settings.")
        return False
    
    config['imap'] = {"server": server, "user": user, "password": password}
    logger.debug("IMAP credentials stored (password not logged).")

    folders = temp_client.list_folders()
    print("\nAvailable IMAP Folders:")
    for i, folder in enumerate(folders):
        print(f"  {i+1}. {folder}")
    
    selected_indices = input("\n2. Folders to Scan (comma-separated numbers, e.g., 1,3): ")
    source_folders = [folders[int(i)-1] for i in selected_indices.split(',')]
    config['imap']['source_folders'] = source_folders
    logger.debug("Source folders set: %s", source_folders)

    temp_client.disconnect()
    logger.debug("Temporary IMAP client disconnected.")

    print("\n3. Translation Settings")
    langs_input = input("Languages to *not* translate (comma-separated, e.g., en,es): ")
    non_translate_langs = [lang.strip().lower() for lang in langs_input.split(',')]
    
    target_lang = ""
    while target_lang not in non_translate_langs:
        target_lang = input(f"Target language (must be one of [{','.join(non_translate_langs)}]): ").strip().lower()
        if target_lang not in non_translate_langs:
            print("Invalid selection. Please choose from your list.")
            
    config['translation'] = {
        "non_translate_languages": non_translate_langs,
        "target_language": target_lang
    }
    logger.debug("Translation settings saved.")
    
    print("\n4. OpenAI API Key")
    api_key = getpass.getpass("Enter your OpenAI API Key: ")
    config['openai'] = {"api_key": api_key}
    logger.debug("OpenAI API key stored (key not logged).")
    
    print("\n5. General Settings")
    interval_map = {"1": 15, "2": 30, "3": 60}
    interval = ""
    while interval not in interval_map:
        interval = input("Check interval (1: 15min, 2: 30min, 3: 1hr): ")
    config['general'] = {"check_interval_minutes": interval_map[interval]}
    logger.debug("Interval set to %s minutes.", interval_map[interval])

    print("\n6. Initial Scan")
    initial_scan_input = input("Do you want to run an initial scan for all existing unread emails now? (y/n): ").strip().lower()
    run_initial_scan = initial_scan_input == 'y'
    config['general']['run_initial_scan'] = run_initial_scan
    logger.debug("Initial scan set to: %s", run_initial_scan)

    print("\n7. Deadline Detection")
    print("This feature uses AI to detect deadlines, events, and dates in emails,")
    print("then automatically creates calendar events (.ics files) attached to translated emails.")
    deadline_detection_input = input("Enable deadline detection for translated emails? (y/n): ").strip().lower()
    enable_deadline_detection = deadline_detection_input == 'y'
    config['general']['enable_deadline_detection'] = enable_deadline_detection
    logger.debug("Deadline detection set to: %s", enable_deadline_detection)

    detect_in_native = False
    if enable_deadline_detection:
        print("\n8. Deadline Detection in Native Language")
        print("Should PigeonHunter also detect deadlines in emails that are already in your language?")
        print("(These won't be translated, but a calendar event will be attached as a new email)")
        native_detection_input = input("Enable deadline detection in native language emails? (y/n): ").strip().lower()
        detect_in_native = native_detection_input == 'y'
        logger.debug("Deadline detection in native language set to: %s", detect_in_native)

    config['general']['detect_deadlines_in_native_language'] = detect_in_native

    save_config(config)
    logger.info("--- Setup Complete! Configuration saved. ---")
    return True