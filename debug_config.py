"""
Debug configuration for PigeonHunter.

Set these flags to True to enable debug features.
"""

# Debug flag: Force scanning of emails starting with "DSPH" (Debug Scan for Pigeon Hunter)
# When enabled:
# - ONLY emails with subjects starting with "DSPH" will be processed
# - All other emails are ignored (even if unread)
# - DSPH emails are processed regardless of read/unread status
# - DSPH emails are NOT added to the processed database (can be tested repeatedly)
# - All PigeonHunter features work normally on DSPH emails
DEBUG_SCAN_DSPH = False
