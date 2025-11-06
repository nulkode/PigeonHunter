# <img src="resources/logo.svg" alt="PigeonHunter Logo" width="48" height="48" align="center" style="vertical-align: middle;"> PigeonHunter

An automated email translation service that monitors IMAP folders and translates incoming emails to your preferred language using OpenAI.

## Features

- Monitors multiple IMAP folders for unread emails
- Automatically translates emails using OpenAI's API
- Preserves original email content alongside translations
- Skips emails already in the target language
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

## License

MIT
