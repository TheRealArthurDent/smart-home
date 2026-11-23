# Packages

One YAML file per topic (presence, lights, shutters, ...), each holding the automations, scripts, helpers and
template sensors of that topic. `configuration.yaml` loads every `*.yaml` here with `!include_dir_named`; the file
name becomes the package name. See <https://www.home-assistant.io/docs/configuration/packages/>.

Long waits are timer helpers, not `delay`, so they survive a restart. No private data (coordinates, phone numbers,
chat ids) goes into these files.
