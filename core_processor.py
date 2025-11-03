import config_manager
import logging
import html

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
    imap_client.save_email("INBOX", subject, html_body)

def process_emails(config, imap_client, translator, db_manager):
    logger.info("Starting email processing run...")
    source_folders = list(config['imap']['source_folders'])
    non_translate_langs = config['translation']['non_translate_languages']
    target_lang = config['translation']['target_language']
    
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
        except Exception as e:
            logger.error("Failed to fetch emails from %s: %s", folder, e, exc_info=True)
            continue 
        
        if not emails:
            logger.info("No new emails in %s.", folder)
            continue
            
        logger.info("Found %d new emails in %s.", len(emails), folder)

        for email in emails:
            
            message_id = email['message_id']
            
            if message_id and db_manager.is_processed(message_id):
                logger.debug("Skipping already processed Message-ID: %s", message_id)
                continue

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

                    imap_client.save_email(
                        folder, 
                        translated_subject,
                        new_html_body,
                        original_message_id=message_id
                    )
                    
                    if message_id:
                        db_manager.add_processed(message_id)
                
                elif result.get('status') == 'skip':
                    logger.info("Skipping email (UID: %s) - Language matched.", email['uid'])
                    if message_id:
                        db_manager.add_processed(message_id)
                
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