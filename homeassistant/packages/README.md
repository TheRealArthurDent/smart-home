# Packages

One YAML file per topic (presence, lights, shutters, ...), each holding the automations, scripts, helpers and
template sensors of that topic. `configuration.yaml` loads every `*.yaml` here with `!include_dir_named`; the file
name becomes the package name. See <https://www.home-assistant.io/docs/configuration/packages/>.

Long waits are timer helpers, not `delay`, so they survive a restart. No private data (coordinates, phone numbers,
chat ids) goes into these files.

`virtual_devices.yaml` is the exception: it includes `homeassistant-virtual/` (mounted at `/config/virtual`), which
the smart_home role fills only on testbench. A device a package uses needs a twin there. `real_devices.yaml` is its
counterpart: it includes `homeassistant-real/` (mounted at `/config/real`), the integrations of the real devices
(Sonos), which the role fills only where there are no twins (raspi).
