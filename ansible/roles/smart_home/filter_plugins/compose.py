"""Compose helpers.

compose_containers: the containers of a Compose project from docker_host_info's verbose container list.

Compose names the service in the label com.docker.compose.service, whose dots Jinja's attribute filters can't
address, so this flattens each container to its service, name and state.

compose_env_value: the value of an env-file line as Compose reads it (tests/test_env_value.py).
"""

import re


def compose_containers(containers, project):
    """Return [{service, name, state}] for the containers labelled with the given Compose project."""
    result = []
    for container in containers or []:
        labels = container.get("Labels") or {}
        if labels.get("com.docker.compose.project") != project:
            continue
        names = container.get("Names") or [""]
        result.append(
            {
                "service": labels.get("com.docker.compose.service", ""),
                "name": names[0].lstrip("/"),
                "state": container.get("State", ""),
            }
        )
    return result


def compose_env_value(raw):
    """The value of an env-file line as Compose reads it, for the quotings the .env files use.

    infrastructure's secrets role writes values double-quoted with `\\`, `"` and `$` escaped (its compose_env
    filter); single quotes are literal; older files hold the value unquoted.
    """
    text = str(raw)
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return re.sub(r"\\(.)", r"\1", text[1:-1], flags=re.DOTALL)
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1]
    return text


class FilterModule:  # pylint: disable=too-few-public-methods
    def filters(self):
        return {"compose_containers": compose_containers, "compose_env_value": compose_env_value}
