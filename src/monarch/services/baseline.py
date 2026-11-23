"""Resolve only a disk baseline or a confirmed layout bound to this session/file."""

from monarch.domain.layout import Layout
from monarch.domain.monitors import Monitor
from monarch.services.state import Paths
from monarch.storage.files import digest, read_json
from monarch.storage.managed import Managed


def known_baseline(
    managed: Managed,
    paths: Paths,
    token: str,
    monitors: tuple[Monitor, ...],
    *,
    allow_topology_rebase: bool = False,
) -> tuple[Layout, bytes]:
    baseline, content = managed.read()
    if paths.confirmed.exists():
        known = read_json(paths.confirmed)
        if (
            isinstance(known, dict)
            and known.get("root") == str(managed.directory)
            and known.get("disk_digest") == digest(content)
            and known.get("session_token") == token
        ):
            confirmed = Layout.parse(known["layout"])
            saved = {(o.name, o.make, o.model, o.serial) for o in confirmed.outputs}
            connected = {(m.name, m.make, m.model, m.serial) for m in monitors}
            if confirmed.matches(monitors) or (allow_topology_rebase and saved != connected):
                # Only a separately authorized topology rebase can snapshot new
                # geometry. Existing explicit policies stay bound to identities.
                baseline = confirmed
    return baseline, content
