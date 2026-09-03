"""Constants for the EDC sharing integration."""

from datetime import date, timedelta

DOMAIN = "edc_sharing"

CONF_SSE_ID = "sse_id"
CONF_SSE_NAME = "sse_name"
CONF_SALE_PRICE = "sale_price"
CONF_REPORT_TARGETS = "report_targets"
CONF_DAILY_REPORT = "daily_report"
CONF_WEEKLY_REPORT = "weekly_report"
CONF_MONTHLY_REPORT = "monthly_report"
CONF_YEARLY_REPORT = "yearly_report"
CONF_SUMMARY_REPORT = "summary_report"
CONF_REPORT_TIME = "report_time"
CONF_REPORT_DAY = "report_day"
CONF_REPORT_LANGUAGE = "report_language"

DEFAULT_SALE_PRICE = 2.0
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
DEFAULT_REPORT_TIME = "07:30:00"
DEFAULT_REPORT_DAY = 5
HISTORY_SCAN_START_DATE = date(2024, 7, 1)

API_BASE_URL = "https://api.portal.edc-cr.cz/api/v0"
AUTHORITY_URL = "https://sso.portal.edc-cr.cz/auth/realms/edc"
CLIENT_ID = "a63c22a3-6e1d-4eac-b383-d06373da046a"
REDIRECT_URI = "https://portal.edc-cr.cz/"


def config_entry_unique_id(username: str, sse_id: str | int) -> str:
    """Return an account-and-group unique ID for one config entry."""
    return f"{username.strip().casefold()}:{sse_id}"
