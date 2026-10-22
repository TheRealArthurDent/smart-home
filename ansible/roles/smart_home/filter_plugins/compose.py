"""compose_containers: the containers of a Compose project from docker_host_info's verbose container list.

Compose names the service in the label com.docker.compose.service, whose dots Jinja's attribute filters can't
address, so this flattens each container to its service, name and state.
"""


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


class FilterModule:  # pylint: disable=too-few-public-methods
    def filters(self):
        return {"compose_containers": compose_containers}
