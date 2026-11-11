"""Lab engine: turns a topology into Docker containers and point-to-point networks.

Only the Docker API is used (no host root, no nsenter), so LabForge runs anywhere Docker runs:
a laptop, a CI runner, a VM, or a Kubernetes node with a Docker/containerd socket.
"""

from __future__ import annotations

import io
import logging
import shlex
import tarfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import docker
from docker.errors import APIError, ImageNotFound, NotFound

from .kinds import KINDS
from .models import Topology
from .netalloc import free_subnets
from .settings import settings

log = logging.getLogger("labforge.engine")
LABEL = "labforge.lab"
Logger = Callable[[str, str], None]


class EngineError(RuntimeError):
    pass


def _tar(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(path.lstrip("/"))
            info.size = len(data)
            info.mode = 0o644
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class Engine:
    def __init__(self, client: docker.DockerClient | None = None, instance: str = ""):
        self._client = client
        self.instance = instance  # labels every resource, so two LabForge installs on one host never collide

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env(timeout=120)
        return self._client

    def ping(self) -> dict:
        try:
            v = self.client.version()
            return {"ok": True, "version": v.get("Version"), "api": v.get("ApiVersion")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    # ---- images -----------------------------------------------------------------------------------------
    def image_present(self, ref: str) -> bool:
        try:
            self.client.images.get(ref)
            return True
        except ImageNotFound:
            return False
        except Exception:  # noqa: BLE001
            return False

    def resolve_image(self, kind: str, logger: Logger | None = None, pull: bool = True) -> str:
        candidates = KINDS[kind].images
        for ref in candidates:
            if self.image_present(ref):
                return ref
        if pull:
            for ref in candidates:
                try:
                    if logger:
                        logger(f"Pulling image {ref} (first use only)", "info")
                    self.client.images.pull(ref)
                    return ref
                except (APIError, NotFound) as e:
                    if logger:
                        logger(f"Could not pull {ref}: {str(e).splitlines()[0][:140]}", "warn")
        raise EngineError(f"no image available for kind '{kind}' (tried: {', '.join(candidates)})")

    # ---- deploy -----------------------------------------------------------------------------------------
    def _taken_subnets(self) -> list[str]:
        out = []
        for n in self.client.networks.list():
            for cfg in (n.attrs.get("IPAM") or {}).get("Config") or []:
                if cfg.get("Subnet"):
                    out.append(cfg["Subnet"])
        return out

    def deploy(self, lab_id: str, topo: Topology, logger: Logger) -> dict:
        labels = {LABEL: lab_id, "labforge.template": topo.id, "labforge.instance": self.instance}
        t0 = time.time()

        images = {}
        for kind in sorted({n.kind for n in topo.nodes.values()}):
            images[kind] = self.resolve_image(kind, logger)

        taken = self._taken_subnets()
        mgmt_subnet = next(free_subnets(settings.mgmt_pool, 24, taken), None)
        if not mgmt_subnet:
            raise EngineError("management address pool exhausted")
        taken.append(mgmt_subnet)
        mgmt = self.client.networks.create(
            f"lf-{lab_id}-mgmt", driver="bridge", internal=True, labels=labels,
            ipam=docker.types.IPAMConfig(pool_configs=[docker.types.IPAMPool(subnet=mgmt_subnet)]),
        )

        link_subnets = free_subnets(settings.link_pool, 29, taken)
        link_nets: dict[str, str] = {}  # "node:ethN" -> network name
        for i, (a, b) in enumerate(topo.links):
            subnet = next(link_subnets, None)
            if not subnet:
                raise EngineError("link address pool exhausted")
            name = f"lf-{lab_id}-l{i + 1}"
            self.client.networks.create(
                name, driver="bridge", internal=False, labels={**labels, "labforge.link": f"{a}--{b}"},
                ipam=docker.types.IPAMConfig(pool_configs=[docker.types.IPAMPool(subnet=subnet)]),
                # Not "internal": Docker would then drop any traffic outside its own subnet, i.e. all of ours.
                options={"com.docker.network.bridge.inhibit_ipv4": "true",
                         "com.docker.network.bridge.enable_ip_masquerade": "false",
                         "com.docker.network.driver.mtu": "1500"},
            )
            link_nets[a] = link_nets[b] = name
        logger(f"Created management network {mgmt_subnet} and {len(topo.links)} links", "info")

        containers = {}
        for node_name, node in topo.nodes.items():
            kind = KINDS[node.kind]
            c = self.client.containers.create(
                images[node.kind], command=kind.command, name=f"lf-{lab_id}-{node_name}",
                hostname=node_name, labels={**labels, "labforge.node": node_name, "labforge.kind": node.kind},
                cap_add=kind.caps, sysctls=kind.sysctls or None, network=mgmt.name, detach=True,
                tty=False, stdin_open=False, mem_limit=f"{max(kind.mem_mb * 4, 128)}m",
                init=node.kind != "router",
            )
            for iface in topo.node_links(node_name):
                self.client.networks.get(link_nets[f"{node_name}:{iface}"]).connect(
                    c, driver_opt={"com.docker.network.endpoint.ifname": iface}
                )
            files = kind.files(node_name, node)
            if files:
                c.put_archive("/", _tar(files))
            containers[node_name] = c
        logger(f"Created {len(containers)} devices", "info")

        for c in containers.values():
            c.start()
        logger("Booted all devices, configuring interfaces", "info")

        def boot(node_name: str) -> None:
            node = topo.nodes[node_name]
            c = containers[node_name]
            c.reload()
            script = ["set -e"] + self._wire_cmds(c, topo, node_name) + KINDS[node.kind].bootstrap(node_name, node)
            script += [f"setsid nohup sh -c {shlex.quote(s)} >/dev/null 2>&1 &" for s in node.startup]
            code, out = c.exec_run(["sh", "-c", "\n".join(script)])
            if code != 0:
                raise EngineError(f"{node_name}: bootstrap failed: {out.decode(errors='replace')[-400:]}")
            self._await_ready(c, node_name, KINDS[node.kind], logger)

        with ThreadPoolExecutor(max_workers=8) as pool:
            for f in [pool.submit(boot, n) for n in topo.nodes]:
                f.result()

        logger(f"Lab ready in {time.time() - t0:.1f}s", "success")
        return {"mgmt_subnet": mgmt_subnet, "images": images}

    @staticmethod
    def _await_ready(c, node_name: str, kind, logger: Logger, attempts: int = 3, wait: float = 8.0) -> None:
        if not kind.ready_cmd:
            return
        for attempt in range(attempts):
            deadline = time.time() + wait
            while time.time() < deadline:
                if c.exec_run(["sh", "-c", kind.ready_cmd])[0] == 0:
                    return
                time.sleep(0.4)
            if kind.recover_cmd and attempt < attempts - 1:
                logger(f"{node_name}: a routing daemon did not start, restarting it", "warn")
                c.exec_run(["sh", "-c", kind.recover_cmd])
        raise EngineError(f"{node_name}: device did not become ready")

    def _wire_cmds(self, c, topo: Topology, node_name: str) -> list[str]:
        """Make sure each link interface carries the name the topology expects, then strip Docker's IP."""
        # Delete Docker's default route explicitly first: a route that vanishes implicitly (address flush)
        # sends no netlink event, so the routing daemon would keep a stale copy and prefer it.
        cmds = ["ip route del default 2>/dev/null || true"]
        nets = c.attrs["NetworkSettings"]["Networks"]
        for iface in topo.node_links(node_name):
            net = nets.get(f"lf-{c.labels[LABEL]}-l{self._link_index(topo, node_name, iface)}")
            mac = (net or {}).get("MacAddress")
            if mac:  # Docker < 28 ignores the ifname option: rename by MAC.
                cmds.append(
                    f'cur=$(ip -o link | awk -F": " \'tolower($0) ~ /{mac.lower()}/ {{print $2}}\' | cut -d@ -f1); '
                    f'if [ -n "$cur" ] && [ "$cur" != "{iface}" ]; then ip link set "$cur" down; '
                    f'ip link set "$cur" name {iface}; fi'
                )
            cmds += [f"ip -4 addr flush dev {iface}", f"ip link set {iface} up"]
        return cmds

    @staticmethod
    def _link_index(topo: Topology, node: str, iface: str) -> int:
        end = f"{node}:{iface}"
        for i, (a, b) in enumerate(topo.links):
            if end in (a, b):
                return i + 1
        raise KeyError(end)

    # ---- teardown ---------------------------------------------------------------------------------------
    def destroy(self, lab_id: str) -> int:
        flt = {"label": f"{LABEL}={lab_id}"}
        cs = self.client.containers.list(all=True, filters=flt)

        def rm(c):
            try:
                c.remove(force=True)
            except NotFound:
                pass

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(rm, cs))
        for n in self.client.networks.list(filters=flt):
            try:
                n.remove()
            except NotFound:
                pass
        return len(cs)

    def lab_ids(self) -> set[str]:
        """Labs that have resources on this Docker host and belong to this LabForge instance."""
        flt = {"label": [LABEL, f"labforge.instance={self.instance}"]}
        ids = {c.labels.get(LABEL) for c in self.client.containers.list(all=True, filters=flt)}
        ids |= {(n.attrs.get("Labels") or {}).get(LABEL) for n in self.client.networks.list(filters=flt)}
        return {i for i in ids if i}

    # ---- day-2 ------------------------------------------------------------------------------------------
    def container(self, lab_id: str, node: str):
        try:
            return self.client.containers.get(f"lf-{lab_id}-{node}")
        except NotFound as e:
            raise EngineError(f"node '{node}' is not running") from e

    def exec(self, lab_id: str, node: str, cmd: list[str] | str) -> tuple[int, str]:
        if isinstance(cmd, str):
            cmd = ["sh", "-c", cmd]
        code, out = self.container(lab_id, node).exec_run(cmd, demux=False)
        return code, (out or b"").decode(errors="replace")

    def node_states(self, lab_id: str) -> dict[str, dict]:
        out = {}
        for c in self.client.containers.list(all=True, filters={"label": f"{LABEL}={lab_id}"}):
            st = c.attrs.get("State", {})
            out[c.labels.get("labforge.node")] = {
                "state": st.get("Status"), "started_at": st.get("StartedAt"),
                "image": c.attrs.get("Config", {}).get("Image"), "container": c.name,
                "mgmt_ip": (c.attrs["NetworkSettings"]["Networks"].get(f"lf-{lab_id}-mgmt") or {}).get("IPAddress"),
            }
        return out

    def open_shell(self, lab_id: str, node: str, cmd: list[str]):
        """Start an interactive TTY exec. Returns (exec_id, raw socket)."""
        c = self.container(lab_id, node)
        api = self.client.api
        ex = api.exec_create(c.id, cmd, stdin=True, tty=True, environment={"TERM": "xterm-256color"})
        sock = api.exec_start(ex["Id"], tty=True, socket=True)
        return ex["Id"], getattr(sock, "_sock", sock)

    def resize_shell(self, exec_id: str, rows: int, cols: int) -> None:
        try:
            self.client.api.exec_resize(exec_id, height=rows, width=cols)
        except APIError:
            pass

