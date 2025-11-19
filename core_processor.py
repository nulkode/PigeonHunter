import config_manager
import logging
import html
import debug_config
from deadline_detector import DeadlineDetector

logger = logging.getLogger(__name__)

def handle_missing_folder(folder_name, config, imap_client, translator):
    logger.warning("Monitored folder '%s' not found. It will be removed from config.", folder_name)
    
    subject = f"PigeonHunter Warning: Folder Removed"
    body_text = f"""
The folder '{folder_name}' was not found on the IMAP server.
It has been automatically removed from the list of folders to scan.

To re-add it or change settings, please restart the application after fixing the folder or edit your config file.
"""
    target_lang = config['translation']['target_language']
    
    if target_lang != 'en':
        try:
            logger.debug("Translating missing folder notification to %s.", target_lang)
            subject = translator.translate_text(subject, target_lang)
            body_text = translator.translate_text(body_text, target_lang)
        except Exception as e:
            logger.error("Could not translate notification email: %s", e, exc_info=True)

    html_body = f"<pre>{html.escape(body_text)}</pre>"
    new_message_id = imap_client.save_email("INBOX", subject, html_body)

def process_emails(config, imap_client, translator, db_manager, deadline_detector=None):
    logger.info("Starting email processing run...")
    source_folders = list(config['imap']['source_folders'])
    non_translate_langs = config['translation']['non_translate_languages']
    target_lang = config['translation']['target_language']

    # Deadline detection settings
    enable_deadline_detection = config.get('general', {}).get('enable_deadline_detection', False)
    detect_in_native = config.get('general', {}).get('detect_deadlines_in_native_language', False)

    folders_to_remove = []

    for folder in source_folders: 
        logger.debug("Checking folder: %s", folder)
        if not imap_client.check_folder_exists(folder):
            handle_missing_folder(folder, config, imap_client, translator)
            folders_to_remove.append(folder)
            continue
        
        logger.info("Scanning folder: %s", folder)
        try:
            emails = imap_client.fetch_unread_emails(folder)

            # Also fetch DSPH debug emails if debug mode is enabled
            if debug_config.DEBUG_SCAN_DSPH:
                dsph_emails = imap_client.fetch_dsph_debug_emails(folder)
                if dsph_emails:
                    logger.info("DEBUG MODE: Found %d DSPH debug email(s) in %s", len(dsph_emails), folder)
                    # Merge DSPH emails with regular emails, avoiding duplicates by UID
                    existing_uids = {email['uid'] for email in emails}
                    for dsph_email in dsph_emails:
                        if dsph_email['uid'] not in existing_uids:
                            emails.append(dsph_email)
        except Exception as e:
            logger.error("Failed to fetch emails from %s: %s", folder, e, exc_info=True)
            continue

        if not emails:
            logger.info("No new emails in %s.", folder)
            continue

        logger.info("Found %d email(s) to process in %s.", len(emails), folder)

        for email in emails:

            message_id = email['message_id']

            # Check if this is a debug DSPH email
            is_debug_dsph = debug_config.DEBUG_SCAN_DSPH and email['subject'].startswith("DSPH")

            # Skip processed emails UNLESS it's a debug DSPH email
            if not is_debug_dsph and message_id and db_manager.is_processed(message_id):
                logger.debug("Skipping already processed Message-ID: %s", message_id)
                continue

            if is_debug_dsph:
                logger.info("DEBUG MODE: Processing DSPH email regardless of processed status (UID: %s)", email['uid'])

            logger.debug("Processing email UID %s (Subject: %s)", email['uid'], email['subject'])

            try:
                result = translator.translate_email(
                    email['subject'],
                    email['rendered_text'],
                    target_lang,
                    non_translate_langs
                )

                if result.get('status') == 'translated':
                    logger.info("Translating email (UID: %s).", email['uid'])

                    translated_subject = result['subject']

                    escaped_translation = html.escape(result['body'])
                    final_translation_html = escaped_translation.replace('\n', '<br>\n')

                    ref_html = ""
                    if message_id:
                        ref_html = f"""
                        <hr>
                        <p style="font-family: sans-serif; font-weight: bold;">Original Message:</p>
                        """
                    else:
                        ref_html = f"""
                        <hr>
                        <p style="font-family: sans-serif; font-weight: bold;">Original Message:</p>
                        """

                    new_html_body = f"""
                    <html>
                    <head>
                        <style>
                            .pigeon-translation {{
                                font-family: sans-serif;
                                /* white-space: pre-wrap; ya no es necesario */
                                margin-bottom: 20px;
                                padding: 15px;
                                border: 1px solid #007bff;
                                background-color: #f8f9fa;
                                border-radius: 5px;
                            }}
                            .pigeon-original {{
                                margin-top: 20px;
                                border: 1px solid #ccc;
                                padding: 10px;
                                opacity: 0.9;
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="pigeon-translation">
                            {final_translation_html}
                        </div>

                        {ref_html}

                        <div class="pigeon-original">
                            {email['original_html']}
                        </div>
                    </body>
                    </html>
                    """

                    # Detect deadlines for translated emails
                    attachments = []
                    if deadline_detector and (enable_deadline_detection or is_debug_dsph):
                        logger.debug("Detecting deadlines for translated email")
                        calendar_events = deadline_detector.process_email_deadlines(
                            email['subject'],
                            email['rendered_text'],
                            target_lang
                        )
                        for deadline_info, ics_content in calendar_events:
                            event_title = deadline_info.get('title', 'Event')
                            attachments.append({
                                'filename': f"{event_title[:30]}.ics",
                                'content': ics_content,
                                'maintype': 'text',
                                'subtype': 'calendar'
                            })
                        if attachments:
                            logger.info("Attaching %d calendar event(s) to translated email", len(attachments))

                    new_message_id = imap_client.save_email(
                        folder,
                        translated_subject,
                        new_html_body,
                        original_message_id=message_id,
                        attachments=attachments if attachments else None
                    )

                    # Don't add debug DSPH emails to processed database so they can be retested
                    if not is_debug_dsph:
                        if message_id:
                            db_manager.add_processed(message_id)
                        if new_message_id:
                            db_manager.add_processed(new_message_id)
                            logger.debug("Added translated email Message-ID %s to processed list.", new_message_id)
                    else:
                        logger.debug("DEBUG MODE: Not adding DSPH email to processed database for retesting")

                elif result.get('status') == 'skip':
                    logger.info("Skipping email (UID: %s) - Language matched.", email['uid'])

                    # Check if we should detect deadlines in native language emails
                    if deadline_detector and (detect_in_native or is_debug_dsph):
                        logger.debug("Detecting deadlines for native language email")
                        calendar_events = deadline_detector.process_email_deadlines(
                            email['subject'],
                            email['rendered_text'],
                            target_lang
                        )

                        if calendar_events:
                            # Create a minimal email with just calendar attachments
                            attachments = []
                            for deadline_info, ics_content in calendar_events:
                                event_title = deadline_info.get('title', 'Event')
                                attachments.append({
                                    'filename': f"{event_title[:30]}.ics",
                                    'content': ics_content,
                                    'maintype': 'text',
                                    'subtype': 'calendar'
                                })

                            # Create minimal email body
                            calendar_subject = f"📅 Calendar Event from: {email['subject']}"
                            calendar_html = f"""
                            <html>
                            <body>
                                <p style="font-family: sans-serif;">
                                    PigeonHunter detected {len(calendar_events)} deadline(s)/event(s) in this email.
                                    Calendar event(s) are attached.
                                </p>
                            </body>
                            </html>
                            """

                            calendar_message_id = imap_client.save_email(
                                folder,
                                calendar_subject,
                                calendar_html,
                                original_message_id=message_id,
                                attachments=attachments
                            )

                            if calendar_message_id:
                                db_manager.add_processed(calendar_message_id)
                                logger.info("Created calendar event email with %d attachment(s)", len(attachments))

                    # Don't add debug DSPH emails to processed database so they can be retested
                    if not is_debug_dsph and message_id:
                        db_manager.add_processed(message_id)
                    elif is_debug_dsph:
                        logger.debug("DEBUG MODE: Not adding DSPH email to processed database for retesting")
                
                else:
                    logger.error("Error processing email (UID: %s): %s. Will retry next time.", email['uid'], result.get('message'))

            except Exception as e:
                logger.error("Critical error processing email UID %s: %s. Will retry next time.", email['uid'], e, exc_info=True)


    if folders_to_remove:
        logger.warning("Removing missing folders from config: %s", folders_to_remove)
        for folder_name in folders_to_remove:
            config['imap']['source_folders'].remove(folder_name)
        config_manager.save_config(config)
        logger.info("Config updated with removed folders.")