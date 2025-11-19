import schedule
import time
import sys
import os
import logging
import config_manager
import core_processor
import debug_config
from database_manager import DatabaseManager
from imap_client import ImapClient
from translator import Translator
from deadline_detector import DeadlineDetector

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("pigeonhunter.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("imapclient").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

def run_job(config, imap_client, translator, db_manager, deadline_detector=None):
    logger = logging.getLogger(__name__)
    logger.info("Running scheduled job...")

    try:
        if not imap_client.connect():
            logger.error("Failed to connect to IMAP. Skipping this run.")
            return

        core_processor.process_emails(config, imap_client, translator, db_manager, deadline_detector)

    except Exception as e:
        logger.error("An unexpected error occurred during processing: %s", e, exc_info=True)
    finally:
        imap_client.disconnect()
        logger.info("Job finished. Waiting for next run...")

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("--- PigeonHunter is starting up ---")

    config_path = config_manager.get_config_file_path()

    if "--reconfig" in sys.argv:
        logger.info("Reconfiguration requested via --reconfig flag.")
        if config_path.exists():
            try:
                os.remove(config_path)
                logger.info("Existing config.json deleted.")
            except OSError as e:
                logger.error(f"Could not delete config file: {e}. Exiting.")
                sys.exit()
        else:
            logger.info("No existing config file to delete.")
    
    if not config_path.exists():
        logger.warning("No config file found. Running first-time setup.")
        
        if not config_manager.run_first_time_setup():
            logger.error("Configuration setup FAILED. Exiting.")
            sys.exit()
        else:
            logger.info("Setup complete! Configuration saved. Please restart the application to begin.")
            sys.exit()
        
    config = config_manager.load_config()
    if not config:
        logger.critical("Failed to load config. Exiting.")
        sys.exit()
    
    logger.debug("Configuration loaded successfully.")

    try:
        db_manager = DatabaseManager()
        db_manager.create_table()
    except Exception as e:
        logger.critical("Failed to initialize database. Exiting. Error: %s", e)
        sys.exit()

    try:
        imap = ImapClient(
            config['imap']['server'],
            config['imap']['user'],
            config['imap']['password']
        )

        translator = Translator(config['openai']['api_key'])

        # Initialize deadline detector if enabled in config OR if debug mode is active
        deadline_detector = None
        config_enabled = config.get('general', {}).get('enable_deadline_detection', False)

        if config_enabled or debug_config.DEBUG_SCAN_DSPH:
            deadline_detector = DeadlineDetector(config['openai']['api_key'])
            if debug_config.DEBUG_SCAN_DSPH:
                logger.warning("DEBUG MODE: DEBUG_SCAN_DSPH is enabled - will scan DSPH emails regardless of config")
            if config_enabled:
                logger.info("Deadline detection enabled via configuration.")
            if not config_enabled and debug_config.DEBUG_SCAN_DSPH:
                logger.info("Deadline detection enabled for debug DSPH emails only.")
        else:
            logger.info("Deadline detection disabled.")

    except KeyError as e:
        logger.critical("Config file is missing a required key: %s. Exiting.", e)
        sys.exit()
    
    interval = config['general']['check_interval_minutes']
    
    if config['general'].get('run_initial_scan', False):
        logger.info("Performing one-time initial scan as requested by config...")
        run_job(config, imap, translator, db_manager, deadline_detector)

        logger.debug("Disabling 'run_initial_scan' flag in config.")
        config['general']['run_initial_scan'] = False
        config_manager.save_config(config)
        logger.info("Initial scan complete.")

    logger.info(f"Scheduling job every {interval} minutes.")
    print(f"--- PigeonHunter is running ---")
    print(f"Checking folders every {interval} minutes. Press Ctrl+C to stop.")
    print("Logs are being saved to 'pigeonhunter.log'")

    schedule.every(interval).minutes.do(run_job, config, imap, translator, db_manager, deadline_detector)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.warning("\nShutdown signal received. Shutting down PigeonHunter...")
        db_manager.close()
        print("\nShutting down PigeonHunter...")

if __name__ == "__main__":
    main()