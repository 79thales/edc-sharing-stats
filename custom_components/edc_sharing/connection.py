"""Klient HA pro tentýž účet sdílí limity mezi setupem, nastavením a reporty."""

from __future__ import annotations

import hashlib

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import EdcApiClient
from .api_policy import ApiAccountState
from .const import DOMAIN


async def async_get_api_client(hass, username: str, password: str) -> EdcApiClient:
    """Načíst pouze bezpečné čekání, pak vytvořit klienta s paměťovým tokenem.

    Souběžné inicializace se serializují ještě před čtením Store. Žádný
    config/options flow nesmí novým klientem obcházet čekání jiných skupin.
    Heslo ani token nejsou ve sdíleném stavu nebo v názvu souboru.
    """
    accounts = hass.data.setdefault(DOMAIN, {}).setdefault("api_accounts", {})
    key = hashlib.sha256(username.strip().casefold().encode()).hexdigest()
    state = accounts.setdefault(key, ApiAccountState())
    async with state.lock:
        if not state.loaded:
            store = Store(hass, 1, f"{DOMAIN}.api_wait.{key}")
            state.restore(await store.async_load())
            state.persist = store.async_save
            state.loaded = True
    return EdcApiClient(async_get_clientsession(hass), username, password, state)
