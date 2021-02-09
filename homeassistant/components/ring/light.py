"""This component provides HA switch support for Ring Door Bell/Chimes."""
from datetime import timedelta
import logging

import requests

from homeassistant.components.light import LightEntity
from homeassistant.core import callback
import homeassistant.util.dt as dt_util

from . import DOMAIN
from .entity import RingEntityMixin

_LOGGER = logging.getLogger(__name__)


# It takes a few seconds for the API to correctly return an update indicating
# that the changes have been made. Once we request a change (i.e. a light
# being turned on) we simply wait for this time delta before we allow
# updates to take place.

SKIP_UPDATES_DELAY = timedelta(seconds=5)

ON_STATE = "on"
OFF_STATE = "off"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Create the lights for the Ring devices."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    groups = hass.data[DOMAIN][config_entry.entry_id]["groups"]

    lights = []

    for device in devices["stickup_cams"]:
        if device.has_capability("light"):
            lights.append(RingLight(config_entry.entry_id, device))

    for group in groups.values():
        lights.append(RingLight(config_entry.entry_id, group, True))

    async_add_entities(lights)


class RingLight(RingEntityMixin, LightEntity):
    """Creates a switch to turn the ring cameras light on and off."""

    def __init__(self, config_entry_id, device, is_group=False):
        """Initialize the light."""
        super().__init__(config_entry_id, device, is_group)
        self._unique_id = device.id
        self._light_on = False
        self._update_light_state()
        self._no_updates_until = dt_util.utcnow()
        self._is_group = is_group

    async def async_added_to_hass(self):
        """Register callbacks."""
        await super().async_added_to_hass()

        if self._is_group:
            await self.ring_objects["group_health_data"].async_track_device(
                self._device, self._update_callback
            )

    async def async_will_remove_from_hass(self):
        """Disconnect callbacks."""
        await super().async_will_remove_from_hass()

        if self._is_group:
            self.ring_objects["group_health_data"].async_untrack_device(
                self._device, self._update_callback
            )

    @callback
    def _update_callback(self, _data=None):
        """Call update method."""
        if self._no_updates_until > dt_util.utcnow():
            return

        self._update_light_state()
        self.async_write_ha_state()

    @property
    def name(self):
        """Name of the light."""
        if self._is_group:
            return self._device.name
        return f"{self._device.name} light"

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def is_on(self):
        """If the switch is currently on or off."""
        return self._light_on

    def _update_light_state(self):
        """Update local state of lights."""
        if self._is_group:
            self._light_on = self._device.lights
        else:
            self._light_on = self._device.lights == ON_STATE

    def _set_light(self, new_state):
        """Update light state, and causes Home Assistant to correctly update."""
        try:
            if self._is_group:
                if new_state == ON_STATE:
                    self._device.lights = True
                elif new_state == OFF_STATE:
                    self._device.lights = False
                else:
                    _LOGGER.error("Invalid state %s passed to _set_light", new_state)
                    return
            else:
                self._device.lights = new_state
        except requests.Timeout:
            _LOGGER.error("Time out setting %s light to %s", self.entity_id, new_state)
            return

        self._light_on = new_state == ON_STATE
        self._no_updates_until = dt_util.utcnow() + SKIP_UPDATES_DELAY
        self.async_write_ha_state()

    def turn_on(self, **kwargs):
        """Turn the light on for 30 seconds."""
        self._set_light(ON_STATE)

    def turn_off(self, **kwargs):
        """Turn the light off."""
        self._set_light(OFF_STATE)
