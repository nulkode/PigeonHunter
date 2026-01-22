# <img src="resources/logo.svg" alt="PigeonHunter Logo" width="48" height="48" align="center" style="vertical-align: middle;"> PigeonHunter

An automated email translation service that monitors IMAP folders and translates incoming emails to your preferred language using OpenAI.

## Features

- Monitors multiple IMAP folders for unread emails
- Automatically translates emails using OpenAI's API
- Preserves original email content alongside translations
- Skips emails already in the target language
- Automatically detects deadlines, events, and dates in emails
- Creates iCalendar (.ics) files for detected events
- Configurable check intervals
- Tracks processed emails to avoid duplicates

## Requirements

- Python 3.x
- OpenAI API key
- IMAP email account

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Linux/Mac
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Docker

Build the image:

```bash
docker build -t pigeonhunter .
```

First-time setup (runs the interactive wizard and persists config/db/logs to your host):

```bash
docker run -it --rm \
   -v $(pwd)/.pigeonhunter-config:/root/.config/PigeonHunter \
   -v $(pwd)/pigeonhunter.log:/app/pigeonhunter.log \
   pigeonhunter
```

Re-run the wizard later:

```bash
docker run -it --rm \
   -v $(pwd)/.pigeonhunter-config:/root/.config/PigeonHunter \
   -v $(pwd)/pigeonhunter.log:/app/pigeonhunter.log \
   pigeonhunter --reconfig
```

Run the service in the background:

```bash
docker run -d --name pigeonhunter --restart unless-stopped \
   -v $(pwd)/.pigeonhunter-config:/root/.config/PigeonHunter \
   -v $(pwd)/pigeonhunter.log:/app/pigeonhunter.log \
   pigeonhunter
```

Notes:
- The mounted `.pigeonhunter-config` folder keeps your configuration and SQLite database between runs.
- The mounted `pigeonhunter.log` file keeps logs on the host; remove that bind mount if you want logs only inside the container.
- Add `-e TZ=Europe/Paris` (or similar) if you need a specific timezone inside the container.

## Configuration

Run the application for the first time to start the setup wizard:

```bash
python main.py
```

The setup will guide you through configuring:
- IMAP server settings
- OpenAI API key
- Folders to monitor
- Target translation language
- Check interval
- Deadline detection settings (optional)

To reconfigure, use:
```bash
python main.py --reconfig
```

## Usage

Start the service:
```bash
python main.py
```

The application will:
1. Connect to your IMAP server
2. Check configured folders at regular intervals
3. Translate new emails and save them to the same folder
4. Log all activity to `pigeonhunter.log`

Press `Ctrl+C` to stop.

## Deadline Detection

PigeonHunter can automatically detect deadlines, events, and dates in your emails and create calendar events (.ics files) for them.

### How It Works

When enabled, PigeonHunter uses AI to scan emails for:
- Explicit deadlines (e.g., "Submit report by March 15th")
- Event invitations (e.g., "Meeting on Friday at 2 PM")
- Celebrations and holidays
- Any date with associated actions or significance

For each detected event, it creates an iCalendar (.ics) file that includes:
- A meaningful title in your target language
- The full email context
- Properly formatted dates and times
- Timezone information

### Configuration Options

1. **Enable deadline detection for translated emails**: When enabled, calendar events are attached to translated emails
2. **Enable deadline detection in native language emails**: When enabled, creates minimal emails with calendar attachments for emails already in your language (no translation needed)

### Calendar Events

Generated calendar events are:
- Standard iCalendar format (.ics files)
- Compatible with Google Calendar, Outlook, Apple Calendar, and other calendar applications
- Automatically handle:
  - All-day events (when no specific time is mentioned)
  - Timed events with start and end times
  - Automatic end time estimation when only start time is provided
  - Timezone support with UTC fallback

Simply open the attached `.ics` file to add the event to your calendar!

## License

MIT
