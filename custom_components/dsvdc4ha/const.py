"""Constants for the dsvdc4ha integration."""
from __future__ import annotations

DOMAIN = "dsvdc4ha"

ENTRY_TYPE_HUB = "hub"
ENTRY_TYPE_DEVICE = "device"

PLATFORMS = ["sensor", "binary_sensor"]

VDC_HOST_NAME = "KarlKiel's Home Assistant vDC-host"
VDC_HOST_MODEL = "KarlKiel's vDC-host @ Home Assistant"
VDC_HOST_MODEL_UID = "KarlKiel's Home Assistant vDC-host"
VDC_HOST_VENDOR_NAME = "KarlKiel"
VDC_HOST_VENDOR_GUID = "vendorname:KarlKiel"

VDC_NAME = "KarlKiel's Home Assistant DS vDC"
VDC_MODEL = "KarlKiel's generic vDC @ Home Assistant"
VDC_MODEL_UID = "KarlKiel's Home Assistant DS vDC"
VDC_IMPLEMENTATION_ID = "x-KarlKiel-HomeAssistant-vDC"
VDC_DEVICE_ICON_NAME = "KarlKielVDC.png"

CONF_PORT = "port"
CONF_ENTRY_TYPE = "entry_type"
CONF_VDSDS = "vdsds"
CONF_VENDOR_NAME = "vendorName"
CONF_DISPLAY_ID = "displayId"

CLICK_TYPE_NAMES: dict[int, str] = {
    0: "tip_1x", 1: "tip_2x", 2: "tip_3x", 3: "tip_4x",
    4: "hold_start", 5: "hold_repeat", 6: "hold_end",
    7: "click_1x", 8: "click_2x", 9: "click_3x",
    10: "short_long", 11: "local_off", 12: "local_on",
    13: "short_short_long", 14: "local_stop", 15: "local_dim",
}
