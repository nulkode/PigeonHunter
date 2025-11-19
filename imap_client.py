import imapclient
import ssl
import logging
import html2text
import imaplib
import html
from email.message import EmailMessage
from email import message_from_bytes
from email.header import decode_header

logger = logging.getLogger(__name__)

class ImapClient:

    def __init__(self, server, user, password):
        self.server = server
        self.user = user
        self.password = password
        self.client = None
        logger.debug("ImapClient initialized for user %s", self.user)

    def connect(self):
        try:
            if self.client:
                self.client.logout()
        except Exception:
            pass
            
        try:
            logger.info("Connecting to IMAP server: %s", self.server)
            self.client = imapclient.IMAPClient(self.server, ssl=True)
            self.client.login(self.user, self.password)
            logger.info("IMAP connection successful.")
            return True
        except Exception as e:
            logger.error("Failed to connect to IMAP server: %s", e, exc_info=True)
            self.client = None
            return False

    def disconnect(self):
        if self.client:
            logger.debug("Disconnecting from IMAP server.")
            self.client.logout()
            self.client = None

    def _ensure_connection(self):
        if not self.client:
            logger.debug("Client not connected. Connecting...")
            return self.connect()

        try:
            self.client.noop()
            return True
        except (imaplib.IMAP4.abort, ssl.SSLZeroReturnError, BrokenPipeError) as e:
            logger.warning("IMAP connection lost (%s). Reconnecting...", e)
            return self.connect()
        except Exception as e:
            logger.error("Unexpected IMAP error: %s. Reconnecting...", e)
            return self.connect()

    def list_folders(self):
        if not self._ensure_connection():
            return []
        logger.debug("Fetching IMAP folder list.")
        folders = self.client.list_folders()
        folder_names = [folder_info[2] for folder_info in folders]
        logger.debug("Found %d folders.", len(folder_names))
        return folder_names

    def check_folder_exists(self, folder_name):
        if not self._ensure_connection():
            return False
        logger.debug("Checking existence of folder: %s", folder_name)
        return self.client.folder_exists(folder_name)

    def create_folder(self, folder_name):
        if not self._ensure_connection():
            return
        try:
            logger.info("Creating folder: %s", folder_name)
            self.client.create_folder(folder_name)
        except Exception as e:
            logger.warning("Could not create folder '%s': %s", folder_name, e)

    def _get_email_parts(self, msg):
        html_body = None
        text_body = None
        
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                charset = part.get_content_charset() or 'utf-8'
                
                if ctype == 'text/html':
                    html_body = part.get_payload(decode=True).decode(charset, 'ignore')
                elif ctype == 'text/plain':
                    text_body = part.get_payload(decode=True).decode(charset, 'ignore')
        else:
            ctype = msg.get_content_type()
            charset = msg.get_content_charset() or 'utf-8'
            if ctype == 'text/html':
                html_body = msg.get_payload(decode=True).decode(charset, 'ignore')
            elif ctype == 'text/plain':
                text_body = msg.get_payload(decode=True).decode(charset, 'ignore')

        rendered_text = "[Could not parse email body]"
        if html_body:
            logger.debug("Rendering body from HTML...")
            h = html2text.HTML2Text()
            h.ignore_links = True
            h.ignore_images = True
            h.body_width = 0
            rendered_text = h.handle(html_body)
        elif text_body:
            logger.debug("Using text/plain body.")
            rendered_text = text_body

        original_html = html_body if html_body else f"<pre>{html.escape(text_body)}</pre>"

        return rendered_text, original_html


    def _process_email_data(self, msgid, data):
        logger.debug("Fetching email with UID %d.", msgid)
        envelope = data.get(b'ENVELOPE')
        body_data = data.get(b'BODY[]')

        raw_subject = envelope.subject
        if raw_subject:
            decoded_parts = decode_header(raw_subject.decode() if isinstance(raw_subject, bytes) else raw_subject)
            subject_parts = []
            for content, encoding in decoded_parts:
                if isinstance(content, bytes):
                    subject_parts.append(content.decode(encoding or 'utf-8', errors='ignore'))
                else:
                    subject_parts.append(content)
            subject = ''.join(subject_parts)
        else:
            subject = "No Subject"

        from_address = envelope.from_[0] if envelope.from_ else None
        if from_address:
            mailbox = from_address.mailbox.decode() if from_address.mailbox else ""
            host = from_address.host.decode() if from_address.host else ""
            from_email_str = f"{mailbox}@{host}" if host else mailbox
            if from_email_str.lower() == self.user.lower():
                logger.debug("Skipping email UID %d from PigeonHunter itself (from: %s)", msgid, from_email_str)
                return None

        message_id = None
        raw_msg_id = envelope.message_id
        if raw_msg_id:
            message_id = raw_msg_id.decode().strip().strip('<>')
            if not message_id:
                message_id = None

        if not message_id:
            logger.warning("Email UID %d has no valid Message-ID. It will be processed but NOT linked or tracked.", msgid)

        msg = message_from_bytes(body_data)
        rendered_text, original_html = self._get_email_parts(msg)

        return {
            'uid': msgid,
            'subject': subject,
            'rendered_text': rendered_text,
            'original_html': original_html,
            'message_id': message_id,
            'is_debug_dsph': subject.startswith("DSPH")
        }

    def fetch_unread_emails(self, folder_name):
        if not self._ensure_connection():
            return []

        emails_data = []
        try:
            logger.debug("Selecting folder: %s", folder_name)
            self.client.select_folder(folder_name, readonly=True)
            message_ids = self.client.search(['UNSEEN'])

            if not message_ids:
                logger.debug("No unread messages found in %s.", folder_name)
                return []

            logger.debug("Found %d unread message IDs.", len(message_ids))

            for msgid, data in self.client.fetch(message_ids, ['ENVELOPE', 'BODY[]']).items():
                email_data = self._process_email_data(msgid, data)
                if email_data:
                    emails_data.append(email_data)

            return emails_data
        except Exception as e:
            logger.error("Error fetching emails from %s: %s", folder_name, e, exc_info=True)
            return []

    def fetch_dsph_debug_emails(self, folder_name):
        """Fetch all emails (read or unread) with subject starting with DSPH for debug purposes."""
        if not self._ensure_connection():
            return []

        emails_data = []
        try:
            logger.debug("DEBUG MODE: Scanning folder %s for DSPH emails", folder_name)
            self.client.select_folder(folder_name, readonly=True)

            message_ids = self.client.search(['SUBJECT', 'DSPH'])

            if not message_ids:
                logger.debug("No DSPH debug emails found in %s.", folder_name)
                return []

            logger.debug("Found %d DSPH debug email(s).", len(message_ids))

            for msgid, data in self.client.fetch(message_ids, ['ENVELOPE', 'BODY[]']).items():
                email_data = self._process_email_data(msgid, data)
                if email_data and email_data['subject'].startswith("DSPH"):
                    emails_data.append(email_data)

            return emails_data
        except Exception as e:
            logger.error("Error fetching DSPH debug emails from %s: %s", folder_name, e, exc_info=True)
            return []

    def save_email(self, target_folder, subject, html_body, original_message_id=None, attachments=None):
        if not self._ensure_connection():
            logger.error("Failed to save email to %s, no IMAP connection.", target_folder)
            return

        logger.debug("Preparing to save email to %s.", target_folder)
        if not self.check_folder_exists(target_folder):
            self.create_folder(target_folder)

        from email import policy

        custom_policy = policy.default.clone(max_line_length=1000)

        msg = EmailMessage(policy=custom_policy)
        msg['Subject'] = subject
        msg['From'] = f"PigeonHunter <{self.user}>"
        msg['To'] = self.user

        if original_message_id:
            logger.debug("Linking email to original Message-ID: %s", original_message_id)
            formatted_id = f"<{original_message_id.strip('<>')}>"
            msg['In-Reply-To'] = formatted_id
            msg['References'] = formatted_id

        msg.add_alternative(html_body, subtype='html', charset='utf-8')

        if attachments:
            for attachment in attachments:
                filename = attachment.get('filename', 'attachment')
                content = attachment.get('content', '')
                maintype = attachment.get('maintype', 'text')
                subtype = attachment.get('subtype', 'calendar')

                logger.debug("Attaching file: %s (%s/%s)", filename, maintype, subtype)
                msg.add_attachment(
                    content.encode('utf-8') if isinstance(content, str) else content,
                    maintype=maintype,
                    subtype=subtype,
                    filename=filename
                )

        new_message_id = msg.get('Message-ID')
        if new_message_id:
            new_message_id = new_message_id.strip('<>')

        try:
            self.client.select_folder(target_folder)
            self.client.append(target_folder, msg.as_bytes())
            logger.info("Saved new HTML email to %s with subject: %s", target_folder, subject)
            return new_message_id
        except Exception as e:
            logger.error("Failed to save email to %s: %s", target_folder, e, exc_info=True)
            return None