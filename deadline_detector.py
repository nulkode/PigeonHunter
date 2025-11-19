import json
import logging
from datetime import datetime, timedelta
from openai import OpenAI
from icalendar import Calendar, Event
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

class DeadlineDetector:

    def __init__(self, api_key):
        logger.debug("Initializing DeadlineDetector.")
        self.client = OpenAI(api_key=api_key)

    def detect_deadlines(self, subject, body, target_language):
        logger.debug("Detecting deadlines in email (target_lang: %s)", target_language)

        system_prompt = f"""
You are a deadline and event detection assistant. Analyze the provided email for any deadlines, events, appointments, or date-related information.

Extract ALL relevant date-based information including:
- Explicit deadlines (e.g., "Submit by March 15th")
- Event invitations (e.g., "Meeting on Friday at 2 PM")
- Celebrations or holidays mentioned
- Any date with associated action or significance

For each deadline/event found, respond with a JSON array of objects with this structure:
{{
  "title": "Brief, meaningful title in {target_language}",
  "description": "Full context from the email",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM" or null if no time specified,
  "end_time": "HH:MM" or null if not specified,
  "all_day": true/false,
  "timezone": "UTC" or best guess timezone
}}

Rules:
1. If no specific time is mentioned, set "all_day": true and both times to null
2. If only start time is given, estimate a reasonable end time based on context (meetings: +1 hour, deadlines: end of day, etc.)
3. If it's a deadline without specific time, set end_time to "23:59"
4. Title should be concise and in {target_language}
5. Description should include relevant email context
6. If no deadlines/events found, return an empty array: []

Respond ONLY with valid JSON.
"""

        user_prompt = f"""
Email to analyze:
Subject: {subject}
Body:
{body}
"""

        try:
            logger.debug("Sending deadline detection request to OpenAI...")
            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            result = json.loads(response.choices[0].message.content)

            if isinstance(result, dict) and "events" in result:
                deadlines = result["events"]
            elif isinstance(result, dict) and "deadlines" in result:
                deadlines = result["deadlines"]
            elif isinstance(result, list):
                deadlines = result
            else:
                deadlines = []

            logger.info("Detected %d deadline(s)/event(s) in email", len(deadlines))
            return deadlines

        except Exception as e:
            logger.error("Error during deadline detection: %s", e, exc_info=True)
            return []

    def create_calendar_event(self, deadline_info, email_subject, email_body):
        try:
            cal = Calendar()
            cal.add('prodid', '-//PigeonHunter Email Deadline//EN')
            cal.add('version', '2.0')

            event = Event()
            event.add('summary', deadline_info['title'])

            description = f"{deadline_info.get('description', '')}\n\n"
            description += f"--- Original Email ---\n"
            description += f"Subject: {email_subject}\n"
            description += f"Content: {email_body[:500]}..."
            event.add('description', description)

            date_str = deadline_info['date']
            event_date = datetime.strptime(date_str, '%Y-%m-%d')

            tz_str = deadline_info.get('timezone', 'UTC')
            try:
                tz = ZoneInfo(tz_str)
            except Exception:
                logger.warning("Invalid timezone '%s', using UTC", tz_str)
                tz = ZoneInfo('UTC')

            if deadline_info.get('all_day', False):
                event.add('dtstart', event_date.date())
                event.add('dtend', (event_date + timedelta(days=1)).date())
                logger.debug("Created all-day event for %s", date_str)
            else:
                start_time = deadline_info.get('start_time')
                end_time = deadline_info.get('end_time')

                if start_time:
                    hour, minute = map(int, start_time.split(':'))
                    start_dt = event_date.replace(hour=hour, minute=minute, tzinfo=tz)
                    event.add('dtstart', start_dt)

                    if end_time:
                        hour, minute = map(int, end_time.split(':'))
                        end_dt = event_date.replace(hour=hour, minute=minute, tzinfo=tz)
                    else:
                        end_dt = start_dt + timedelta(hours=1)

                    event.add('dtend', end_dt)
                    logger.debug("Created timed event from %s to %s", start_time, end_time or "estimated")
                else:
                    event.add('dtstart', event_date.date())
                    event.add('dtend', (event_date + timedelta(days=1)).date())

            cal.add_component(event)

            return cal.to_ical().decode('utf-8')

        except Exception as e:
            logger.error("Error creating calendar event: %s", e, exc_info=True)
            return None

    def process_email_deadlines(self, subject, body, target_language):
        deadlines = self.detect_deadlines(subject, body, target_language)

        if not deadlines:
            return []

        results = []
        for deadline in deadlines:
            ics_content = self.create_calendar_event(deadline, subject, body)
            if ics_content:
                results.append((deadline, ics_content))

        logger.info("Generated %d calendar event(s) from detected deadlines", len(results))
        return results
