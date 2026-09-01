"""Constants for the EDC sharing integration."""

from datetime import timedelta

DOMAIN = "edc_sharing"

CONF_SSE_ID = "sse_id"
CONF_SSE_NAME = "sse_name"
CONF_SALE_PRICE = "sale_price"

DEFAULT_SALE_PRICE = 2.0
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)

API_BASE_URL = "https://api.portal.edc-cr.cz/api/v0"
AUTHORITY_URL = "https://sso.portal.edc-cr.cz/auth/realms/edc"
CLIENT_ID = "a63c22a3-6e1d-4eac-b383-d06373da046a"
REDIRECT_URI = "https://portal.edc-cr.cz/"
