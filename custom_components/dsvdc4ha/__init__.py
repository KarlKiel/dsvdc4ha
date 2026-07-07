"""dSVDC Home Assistant integration."""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ._icon_utils import MDI_DOMAIN_ICONS, bundled_icon_b64
from .const import DOMAIN, PLATFORMS
from .coordinator import HubCoordinator

_LOGGER = logging.getLogger(__name__)

_MANIFEST = json.loads((pathlib.Path(__file__).parent / "manifest.json").read_text())
_PYDSVDCAPI_REQ: str = next(
    r for r in _MANIFEST["requirements"] if r.startswith("pydsvdcapi")
)


def _pydsvdcapi_needs_update(requirement: str) -> bool:
    """Return True when the installed pydsvdcapi version doesn't match *requirement*."""
    import importlib.metadata

    if "==" not in requirement:
        return False
    pkg_name, required_version = requirement.split("==", 1)
    try:
        installed = importlib.metadata.version(pkg_name)
        return installed != required_version
    except importlib.metadata.PackageNotFoundError:
        return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Ensure the pinned pydsvdcapi version is installed before any entry setup."""
    from homeassistant.util.package import install_package

    if await hass.async_add_executor_job(_pydsvdcapi_needs_update, _PYDSVDCAPI_REQ):
        _LOGGER.info("Installing/updating required package: %s", _PYDSVDCAPI_REQ)
        success = await hass.async_add_executor_job(install_package, _PYDSVDCAPI_REQ)
        if not success:
            _LOGGER.error(
                "Failed to install %s — the integration may not work correctly",
                _PYDSVDCAPI_REQ,
            )
    return True


def _entity_ids_in_vdsd(vdsd_data: dict[str, Any]) -> set[str]:
    """Return all HA entity_ids referenced by a single vdSD config dict."""
    ids: set[str] = set()
    if output := vdsd_data.get("output"):
        for ch in output.get("channels", []):
            if eid := ch.get("read_entity"):
                ids.add(eid)
    for key in ("binary_inputs", "sensors", "buttons"):
        for comp in vdsd_data.get(key, []):
            if eid := comp.get("callback_entity"):
                ids.add(eid)
    return ids


def _build_entity_index(entry: ConfigEntry) -> dict[str, list[tuple[str, int]]]:
    """Map entity_id → [(subentry_id, vdsd_idx), …] for all subentries."""
    index: dict[str, list[tuple[str, int]]] = {}
    for subentry in entry.subentries.values():
        for vdsd_idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
            for eid in _entity_ids_in_vdsd(vdsd_data):
                index.setdefault(eid, []).append((subentry.subentry_id, vdsd_idx))
    return index


async def _backfill_missing_icons(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Backfill/upgrade icon_data_b64 for vdSDs missing an icon_slug (old-format entries).

    New-format entries store icon_slug alongside icon_data_b64 so this backfill
    skips them.  Old-format entries (no icon_slug key) are upgraded to the best
    device-class-specific bundled icon available, which covers all supported
    device classes now that the bundled PNG set is complete.
    """
    for subentry in entry.subentries.values():
        vdsds = list(subentry.data.get("vdsds", []))
        updated = False
        for i, vdsd in enumerate(vdsds):
            if "icon_slug" in vdsd:
                continue  # Already processed by new-format config flow
            for eid in _entity_ids_in_vdsd(vdsd):
                state = hass.states.get(eid)
                if state is None:
                    continue
                domain = eid.split(".")[0]
                device_class = state.attributes.get("device_class")
                slug = MDI_DOMAIN_ICONS.get(f"{domain}.{device_class}") if device_class else None
                slug = slug or MDI_DOMAIN_ICONS.get(domain)
                b64 = bundled_icon_b64(slug) if slug else None
                if b64:
                    vdsds[i] = {**vdsd, "icon_data_b64": b64, "icon_slug": slug}
                else:
                    vdsds[i] = {**vdsd, "icon_slug": slug}
                updated = True
                break
        if updated:
            hass.config_entries.async_update_subentry(
                entry, subentry, data={**subentry.data, "vdsds": vdsds}
            )


def _scalar(val: Any) -> bool:
    return isinstance(val, (int, float, bool, str)) and val is not None


# Human-readable labels for ALL property keys (settings + diagnostic)
_PROP_DISPLAY: dict[str, str] = {
    # vdSD common
    "dSUID": "Device UID",
    "displayId": "Display ID",
    "model": "Model",
    "modelVersion": "Model Version",
    "modelUID": "Model UID",
    "hardwareVersion": "Hardware Version",
    "hardwareGuid": "Hardware GUID",
    "hardwareModelGuid": "Hardware Model GUID",
    "vendorName": "Vendor",
    "vendorId": "Vendor ID",
    "vendorGuid": "Vendor GUID",
    "oemGuid": "OEM GUID",
    "oemModelGuid": "OEM Model GUID",
    "configURL": "Config URL",
    "deviceIconName": "Device Icon",
    "deviceClass": "Device Class",
    "deviceClassVersion": "Device Class Version",
    "primaryGroup": "Primary Group",
    "currentConfigId": "Config ID",
    # Input descriptions
    "inputType": "Input Type",
    "inputUsage": "Input Usage",
    "sensorFunction": "Sensor Function",
    "sensorType": "Sensor Type",
    "sensorUsage": "Sensor Usage",
    "updateInterval": "Update Interval",
    "aliveSignInterval": "Alive Sign Interval",
    "min": "Min Value",
    "max": "Max Value",
    "resolution": "Resolution",
    # Button descriptions
    "supportsLocalKeyMode": "Local Key Mode",
    "buttonType": "Button Type",
    "buttonElementID": "Button Element ID",
    "buttonID": "Button ID",
    # Output descriptions
    "function": "Function",
    "outputUsage": "Output Usage",
    "variableRamp": "Variable Ramp",
    "maxPower": "Max Power",
    "defaultGroup": "Default Group",
    "activeCoolingMode": "Active Cooling",
    # State
    "clickType": "Click Type",
    "actionId": "Action ID",
    "actionMode": "Action Mode",
    "localPriority": "Local Priority",
    "transitionTime": "Transition Time",
    "contextId": "Context ID",
    "contextMsg": "Context",
    "error": "Error State",
    # Settings (writable)
    "group": "Group",
    "setsLocalPriority": "Sets Local Priority",
    "callsPresent": "Calls Present",
    "mode": "Mode",
    "channel": "Channel",
    "minPushInterval": "Min Push Interval",
    "changesOnlyInterval": "Changes Only Interval",
    "activeGroup": "Active Group",
    "pushChanges": "Push Changes",
    "onThreshold": "On Threshold",
    "minBrightness": "Min Brightness",
    "dimTimeUp": "Dim Time Up",
    "dimTimeDown": "Dim Time Down",
    "dimTimeUpAlt1": "Dim Time Up Alt 1",
    "dimTimeDownAlt1": "Dim Time Down Alt 1",
    "dimTimeUpAlt2": "Dim Time Up Alt 2",
    "dimTimeDownAlt2": "Dim Time Down Alt 2",
    "heatingSystemCapability": "Heating System Capability",
    "heatingSystemType": "Heating System Type",
    "openTime": "Open Time",
    "closeTime": "Close Time",
    "angleOpenTime": "Angle Open Time",
    "angleCloseTime": "Angle Close Time",
    "stopDelayTime": "Stop Delay Time",
    "name": "Name",
    "zoneID": "Zone ID",
    "progMode": "Programming Mode",
}

# vdSD properties that are writable or internal — excluded from read-only diagnostic sensors.
_VDSD_EXCLUDED_DIAGNOSTIC: frozenset[str] = frozenset({
    "active", "name", "zoneID", "progMode", "type",
})

# Per-input/output property keys always excluded from diagnostic sensors
_INPUT_EXCLUDED_KEYS: frozenset[str] = frozenset({
    "dsIndex", "name", "age", "value", "extendedValue",
})


def _create_property_entities(
    api: Any,
    subentry: Any,
    add_sensor: Any,
    add_number: Any,
    add_select: Any,
    add_switch: Any,
    add_text: Any,
) -> None:
    """Create diagnostic/config sensor entities and all writable setting entities."""
    from homeassistant.helpers.entity import EntityCategory
    from .sensor import PropertySensorEntity
    from .number import WritableSettingNumberEntity
    from .select import SelectableSettingEntity, SETTING_OPTIONS
    from .switch import BoolSettingEntity, BOOL_SETTING_KEYS, VdsdActiveSwitchEntity
    from .text import TextSettingEntity
    from pydsvdcapi.enums import (
        BinaryInputType, BinaryInputUsage, SensorType, SensorUsage,
        ButtonType, ButtonElementID, ButtonClickType, ActionMode,
        OutputFunction, OutputUsage, InputError, OutputError, ColorGroup,
    )

    _ENUM_MAP: dict[tuple[str, str], type] = {
        ("bi", "inputType"): BinaryInputType,
        ("bi", "inputUsage"): BinaryInputUsage,
        ("bi", "sensorFunction"): BinaryInputType,
        ("bi", "error"): InputError,
        ("si", "sensorType"): SensorType,
        ("si", "sensorUsage"): SensorUsage,
        ("si", "error"): InputError,
        ("btn", "buttonType"): ButtonType,
        ("btn", "buttonElementID"): ButtonElementID,
        ("btn", "clickType"): ButtonClickType,
        ("btn", "actionMode"): ActionMode,
        ("btn", "error"): InputError,
        ("out", "function"): OutputFunction,
        ("out", "outputUsage"): OutputUsage,
        ("out", "error"): OutputError,
        ("vdsd", "primaryGroup"): ColorGroup,
    }

    def _resolve(input_type: str, key: str, val: Any) -> Any:
        """Return enum name string if the key maps to a known enum, else raw value."""
        enum_cls = _ENUM_MAP.get((input_type, key))
        if enum_cls is not None:
            try:
                return enum_cls(int(val)).name
            except (ValueError, TypeError):
                pass
        return val

    def _input_prefix(idx: int, count: int, desc_name: str | None, fallback: str) -> str:
        """Return 'Name: ' prefix when count > 1, empty string when count == 1."""
        if count <= 1:
            return ""
        name = (desc_name or "").strip()
        return f"{name or f'{fallback} {idx + 1}'}: "

    for vdsd_idx, vdsd_data in enumerate(subentry.data.get("vdsds", [])):
        device = api.get_device(subentry.subentry_id)
        if not device:
            continue
        vdsd = device.get_vdsd(vdsd_idx)
        if not vdsd:
            continue
        sid = subentry.subentry_id
        prop_entities: list = []
        num_entities: list = []
        sel_entities: list = []
        sw_entities: list = []
        txt_entities: list = []

        # ── vdSD-level diagnostic properties ────────────────────────────────
        for key, val in vdsd.get_properties().items():
            if key in _VDSD_EXCLUDED_DIAGNOSTIC or not _scalar(val):
                continue
            if add_sensor:
                prop_entities.append(PropertySensorEntity(
                    sid, vdsd_idx, vdsd_data,
                    f"vdsd_{key}", _PROP_DISPLAY.get(key, key),
                    _resolve("vdsd", key, val), EntityCategory.DIAGNOSTIC,
                ))

        # ── vdSD writable properties ─────────────────────────────────────────
        if add_switch:
            sw_entities.append(VdsdActiveSwitchEntity(sid, vdsd_idx, vdsd_data, vdsd.active))
        if add_text:
            txt_entities.append(TextSettingEntity(
                sid, vdsd_idx, vdsd_data, "vdsd_name", "Name", vdsd.name,
            ))
        if add_number:
            num_entities.append(WritableSettingNumberEntity(
                sid, vdsd_idx, vdsd_data,
                "vdsd_writable_zoneID", "Zone ID",
                vdsd.zone_id, "vdsd", None, "zoneID",
            ))
        if add_switch and vdsd.prog_mode is not None:
            sw_entities.append(BoolSettingEntity(
                sid, vdsd_idx, vdsd_data,
                "vdsd_writable_progMode", "Programming Mode",
                vdsd.prog_mode, "vdsd", None, "progMode",
            ))

        # ── helper: create one writable setting entity ───────────────────────
        def _make_writable(input_type: str, idx: int | None, key: str, val: Any, prefix: str, label_prefix: str) -> None:
            setting_label = _PROP_DISPLAY.get(key, key)
            display = f"{label_prefix}{setting_label}" if label_prefix else setting_label
            uid = f"{prefix}_writable_{key}"
            opt_key = (input_type, key)
            if opt_key in SETTING_OPTIONS and add_select:
                sel_entities.append(SelectableSettingEntity(
                    sid, vdsd_idx, vdsd_data, uid, display,
                    int(val), input_type, idx, key, SETTING_OPTIONS[opt_key],
                ))
            elif opt_key in BOOL_SETTING_KEYS and add_switch:
                sw_entities.append(BoolSettingEntity(
                    sid, vdsd_idx, vdsd_data, uid, display,
                    val, input_type, idx, key,
                ))
            elif add_number:
                num_entities.append(WritableSettingNumberEntity(
                    sid, vdsd_idx, vdsd_data, uid, display,
                    val, input_type, idx, key,
                ))

        n_bi = len(vdsd.binary_inputs)
        n_si = len(vdsd.sensor_inputs)
        n_btn = len(vdsd.button_inputs)

        # ── binary inputs ────────────────────────────────────────────────────
        for bi_idx, bi in vdsd.binary_inputs.items():
            desc = bi.get_description_properties()
            bi_prefix = _input_prefix(bi_idx, n_bi, desc.get("name"), "Bin.Sensor")
            for key, val in desc.items():
                if key in _INPUT_EXCLUDED_KEYS or not _scalar(val):
                    continue
                if add_sensor:
                    label = f"{bi_prefix}{_PROP_DISPLAY.get(key, key)}"
                    prop_entities.append(PropertySensorEntity(
                        sid, vdsd_idx, vdsd_data,
                        f"bi_{bi_idx}_desc_{key}", label,
                        _resolve("bi", key, val), EntityCategory.DIAGNOSTIC,
                    ))
            for key, val in bi.get_settings_properties().items():
                if _scalar(val):
                    _make_writable("bi", bi_idx, key, val, f"bi_{bi_idx}", bi_prefix)
            for key, val in bi.get_state_properties().items():
                if key in _INPUT_EXCLUDED_KEYS or not _scalar(val):
                    continue
                if add_sensor:
                    label = f"{bi_prefix}{_PROP_DISPLAY.get(key, key)}"
                    prop_entities.append(PropertySensorEntity(
                        sid, vdsd_idx, vdsd_data,
                        f"bi_{bi_idx}_state_{key}", label,
                        _resolve("bi", key, val), EntityCategory.DIAGNOSTIC,
                    ))

        # ── sensor inputs ────────────────────────────────────────────────────
        for si_idx, si in vdsd.sensor_inputs.items():
            desc = si.get_description_properties()
            si_prefix = _input_prefix(si_idx, n_si, desc.get("name"), "Sensor")
            for key, val in desc.items():
                if key in _INPUT_EXCLUDED_KEYS or not _scalar(val):
                    continue
                if add_sensor:
                    label = f"{si_prefix}{_PROP_DISPLAY.get(key, key)}"
                    prop_entities.append(PropertySensorEntity(
                        sid, vdsd_idx, vdsd_data,
                        f"si_{si_idx}_desc_{key}", label,
                        _resolve("si", key, val), EntityCategory.DIAGNOSTIC,
                    ))
            for key, val in si.get_settings_properties().items():
                if _scalar(val):
                    _make_writable("si", si_idx, key, val, f"si_{si_idx}", si_prefix)
            for key, val in si.get_state_properties().items():
                if key in _INPUT_EXCLUDED_KEYS or not _scalar(val):
                    continue
                if add_sensor:
                    label = f"{si_prefix}{_PROP_DISPLAY.get(key, key)}"
                    prop_entities.append(PropertySensorEntity(
                        sid, vdsd_idx, vdsd_data,
                        f"si_{si_idx}_state_{key}", label,
                        _resolve("si", key, val), EntityCategory.DIAGNOSTIC,
                    ))

        # ── button inputs ────────────────────────────────────────────────────
        for btn_idx, btn in vdsd.button_inputs.items():
            desc = btn.get_description_properties()
            btn_prefix = _input_prefix(btn_idx, n_btn, desc.get("name"), "Button")
            for key, val in desc.items():
                if key in _INPUT_EXCLUDED_KEYS or not _scalar(val):
                    continue
                if add_sensor:
                    label = f"{btn_prefix}{_PROP_DISPLAY.get(key, key)}"
                    prop_entities.append(PropertySensorEntity(
                        sid, vdsd_idx, vdsd_data,
                        f"btn_{btn_idx}_desc_{key}", label,
                        _resolve("btn", key, val), EntityCategory.DIAGNOSTIC,
                    ))
            for key, val in btn.get_settings_properties().items():
                if _scalar(val):
                    _make_writable("btn", btn_idx, key, val, f"btn_{btn_idx}", btn_prefix)
            for key, val in btn.get_state_properties().items():
                if key in _INPUT_EXCLUDED_KEYS or not _scalar(val):
                    continue
                if add_sensor:
                    label = f"{btn_prefix}{_PROP_DISPLAY.get(key, key)}"
                    prop_entities.append(PropertySensorEntity(
                        sid, vdsd_idx, vdsd_data,
                        f"btn_{btn_idx}_state_{key}", label,
                        _resolve("btn", key, val), EntityCategory.DIAGNOSTIC,
                    ))

        # ── output ───────────────────────────────────────────────────────────
        if vdsd.output:
            for key, val in vdsd.output.get_description_properties().items():
                if key in _INPUT_EXCLUDED_KEYS or not _scalar(val):
                    continue
                if add_sensor:
                    prop_entities.append(PropertySensorEntity(
                        sid, vdsd_idx, vdsd_data,
                        f"out_desc_{key}", _PROP_DISPLAY.get(key, key),
                        _resolve("out", key, val), EntityCategory.DIAGNOSTIC,
                    ))
            for key, val in vdsd.output.get_state_properties().items():
                if key in _INPUT_EXCLUDED_KEYS or not _scalar(val):
                    continue
                if add_sensor:
                    prop_entities.append(PropertySensorEntity(
                        sid, vdsd_idx, vdsd_data,
                        f"out_state_{key}", _PROP_DISPLAY.get(key, key),
                        _resolve("out", key, val), EntityCategory.DIAGNOSTIC,
                    ))
            for key, val in vdsd.output.get_settings_properties().items():
                if _scalar(val):
                    _make_writable("out", None, key, val, "out", "")

        if prop_entities and add_sensor:
            add_sensor(prop_entities, config_subentry_id=sid)
        if num_entities and add_number:
            add_number(num_entities, config_subentry_id=sid)
        if sel_entities and add_select:
            add_select(sel_entities, config_subentry_id=sid)
        if sw_entities and add_switch:
            add_switch(sw_entities, config_subentry_id=sid)
        if txt_entities and add_text:
            add_text(txt_entities, config_subentry_id=sid)


async def _vanish_deleted_devices(coordinator: HubCoordinator, entry: ConfigEntry) -> None:
    """Vanish devices that were removed from entry.subentries since last setup."""
    if coordinator.api is None:
        return
    current_ids = set(entry.subentries.keys())
    for entry_id in coordinator.api.registered_entry_ids - current_ids:
        try:
            await coordinator.api.vanish_device(entry_id)
        except Exception:
            _LOGGER.warning("Failed to vanish deleted device %s", entry_id, exc_info=True)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # Pick up the already-running coordinator started during config flow (if present).
    pending = hass.data[DOMAIN].pop("_pending_coordinator", None)
    if pending is not None:
        coordinator = pending
    else:
        coordinator = HubCoordinator(hass, port=entry.data["port"])
        try:
            await coordinator.async_start()
        except Exception as exc:
            raise ConfigEntryNotReady(f"Cannot start vDC host: {exc}") from exc
    coordinator._entry = entry
    hass.data[DOMAIN]["hub"] = coordinator

    # Set up sensor / binary_sensor platforms — they iterate entry.subentries
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register, seed initial values, then announce each device subentry.
    # Order matters: add_device first (builds the object graph), then wire up
    # HA→dS listeners, then seed current HA state so pydsvdcapi's
    # _wait_for_initial_values() is satisfied before announce() is awaited.
    await _backfill_missing_icons(hass, entry)
    from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
    dev_reg = dr.async_get(hass)
    internal_url = (hass.config.internal_url or "http://homeassistant.local:8123").rstrip("/")
    for subentry in entry.subentries.values():
        vdsds = subentry.data.get("vdsds", [])
        coordinator.api.add_device(subentry.subentry_id, vdsds)
        # Patch per-vdSD config URLs to point to their individual HA device pages.
        url_map: dict[tuple[str, int], str] = {}
        for vdsd_idx in range(len(vdsds)):
            identifier = (DOMAIN, f"{subentry.subentry_id}_{vdsd_idx}")
            ha_device = dev_reg.async_get_device(identifiers={identifier})
            if ha_device is not None:
                url_map[(subentry.subentry_id, vdsd_idx)] = (
                    f"{internal_url}/config/devices/device/{ha_device.id}"
                )
        if url_map:
            coordinator.api.patch_vdsd_config_urls(url_map)
        unsubs = setup_input_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
        unsubs += setup_output_listeners(hass, coordinator.api, subentry.subentry_id, vdsds)
        hass.data[DOMAIN][subentry.subentry_id] = {"unsubs": unsubs}
        await seed_initial_values(hass, coordinator.api, subentry.subentry_id, vdsds)
        await coordinator.api.announce_device(subentry.subentry_id)

    # Expose vdSD and input property groups as hidden diagnostic/config entities.
    _add_sensor = hass.data[DOMAIN].get("_add_sensor_entities")
    _add_number = hass.data[DOMAIN].get("_add_number_entities")
    _add_select = hass.data[DOMAIN].get("_add_select_entities")
    _add_switch = hass.data[DOMAIN].get("_add_switch_entities")
    _add_text = hass.data[DOMAIN].get("_add_text_entities")
    if coordinator.api and any([_add_sensor, _add_number, _add_select, _add_switch, _add_text]):
        for subentry in entry.subentries.values():
            _create_property_entities(
                coordinator.api, subentry,
                _add_sensor, _add_number, _add_select, _add_switch, _add_text,
            )

    # React to entity enable/disable and deletion in the HA entity registry.
    # Store in domain_data so the subentry delta listener can update it in-place.
    entity_index = _build_entity_index(entry)
    hass.data[DOMAIN]["_entity_index"] = entity_index
    hass.data[DOMAIN]["_known_subentry_ids"] = set(entry.subentries.keys())

    @callback
    def _on_entity_registry_updated(event: Event) -> None:
        action: str = event.data.get("action", "")
        entity_id: str = event.data.get("entity_id", "")
        if entity_id not in entity_index:
            return

        if action == "update" and "disabled_by" in event.data.get("changes", {}):
            reg_entry = er.async_get(hass).async_get(entity_id)
            active = reg_entry is not None and reg_entry.disabled_by is None
            from pydsvdcapi.enums import DeviceLifecycleState
            lc_state = DeviceLifecycleState.ACTIVE if active else DeviceLifecycleState.INACTIVE
            for subentry_id, vdsd_idx in entity_index[entity_id]:
                hass.async_create_task(
                    coordinator.api.set_vdsd_lifecycle(subentry_id, vdsd_idx, lc_state)
                )
        elif action == "remove":
            for subentry_id, _ in entity_index.pop(entity_id, []):
                hass.async_create_task(coordinator.api.vanish_device(subentry_id))

    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _on_entity_registry_updated)
    )

    entry.async_on_unload(entry.add_update_listener(_async_subentry_update_listener))

    return True


async def _async_subentry_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    coordinator: HubCoordinator | None = domain_data.get("hub")
    if coordinator is None or coordinator.api is None:
        return

    known_ids: set[str] = domain_data.get("_known_subentry_ids", set())
    current_ids = set(entry.subentries.keys())
    removed = known_ids - current_ids
    added = current_ids - known_ids

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    for subentry_id in removed:
        await coordinator.api.vanish_device(subentry_id)
        ent_reg.async_clear_config_subentry(entry.entry_id, subentry_id)
        dev_reg.async_clear_config_subentry(entry.entry_id, subentry_id)
        subentry_data = domain_data.pop(subentry_id, {})
        for unsub in subentry_data.get("unsubs", []):
            unsub()

    if added:
        from .listeners import setup_input_listeners, setup_output_listeners, seed_initial_values
        from . import sensor as _sensor_mod
        from . import binary_sensor as _binary_sensor_mod
        from . import button as _button_mod

        add_sensor = domain_data.get("_add_sensor_entities")
        add_binary = domain_data.get("_add_binary_entities")
        add_button = domain_data.get("_add_button_entities")
        add_number = domain_data.get("_add_number_entities")
        add_select = domain_data.get("_add_select_entities")
        add_switch = domain_data.get("_add_switch_entities")
        add_text = domain_data.get("_add_text_entities")

        for subentry_id in added:
            subentry = entry.subentries[subentry_id]
            vdsds = subentry.data.get("vdsds", [])
            coordinator.api.add_device(subentry_id, vdsds)
            unsubs = setup_input_listeners(hass, coordinator.api, subentry_id, vdsds)
            unsubs += setup_output_listeners(hass, coordinator.api, subentry_id, vdsds)
            domain_data[subentry_id] = {"unsubs": unsubs}
            await seed_initial_values(hass, coordinator.api, subentry_id, vdsds)
            await coordinator.api.announce_device(subentry_id)
            if add_sensor:
                _sensor_mod._add_entities_for_subentry(subentry, add_sensor)
            if add_binary:
                _binary_sensor_mod._add_entities_for_subentry(subentry, add_binary)
            if add_button:
                _button_mod._add_entities_for_subentry(subentry, add_button, coordinator)
            if any([add_sensor, add_number, add_select, add_switch, add_text]):
                _create_property_entities(
                    coordinator.api, subentry,
                    add_sensor, add_number, add_select, add_switch, add_text,
                )

    if removed or added:
        entity_index: dict = domain_data.get("_entity_index", {})
        entity_index.clear()
        entity_index.update(_build_entity_index(entry))
        domain_data["_known_subentry_ids"] = current_ids


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.get(DOMAIN, {})

    for subentry in entry.subentries.values():
        subentry_data = domain_data.pop(subentry.subentry_id, {})
        for unsub in subentry_data.get("unsubs", []):
            unsub()

    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator: HubCoordinator | None = domain_data.pop("hub", None)
    if coordinator:
        await _vanish_deleted_devices(coordinator, entry)
        await coordinator.async_stop()

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when the hub config entry is fully deleted."""
    hub: HubCoordinator | None = hass.data.get(DOMAIN, {}).pop("hub", None)
    if hub:
        for subentry in entry.subentries.values():
            await hub.api.vanish_device(subentry.subentry_id)
        await hub.api.stop()
