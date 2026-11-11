"""Topology catalog: built-in templates plus any the team adds (YAML files)."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from .kinds import KINDS
from .models import Topology
from .settings import settings

log = logging.getLogger("labforge.catalog")
BUILTIN = Path(__file__).parent / "catalog"


def _dirs() -> list[tuple[Path, str]]:
    out = [(BUILTIN, "built-in"), (settings.user_catalog, "custom")]
    if settings.extra_catalog:
        out.append((settings.extra_catalog, "custom"))
    return out


def parse(text: str) -> Topology:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("template must be a YAML mapping")
    return Topology.model_validate(data)


def load_all() -> dict[str, tuple[Topology, str]]:
    out: dict[str, tuple[Topology, str]] = {}
    for d, source in _dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.y*ml")):
            try:
                topo = parse(f.read_text())
            except (ValidationError, ValueError, yaml.YAMLError) as e:
                log.warning("skipping invalid template %s: %s", f, e)
                continue
            out[topo.id] = (topo, source)
    return out


def get(template_id: str) -> Topology:
    all_ = load_all()
    if template_id not in all_:
        raise KeyError(template_id)
    return all_[template_id][0]


def save_custom(text: str) -> Topology:
    topo = parse(text)
    settings.user_catalog.mkdir(parents=True, exist_ok=True)
    (settings.user_catalog / f"{topo.id}.yaml").write_text(text)
    return topo


def summary(topo: Topology, source: str = "built-in") -> dict:
    kinds: dict[str, int] = {}
    for n in topo.nodes.values():
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    return {
        "id": topo.id, "name": topo.name, "summary": topo.summary, "description": topo.description,
        "category": topo.category, "difficulty": topo.difficulty, "ttl_minutes": topo.ttl_minutes,
        "tags": topo.tags, "use_cases": topo.use_cases, "source": source,
        "node_count": len(topo.nodes), "link_count": len(topo.links), "check_count": len(topo.checks),
        "kinds": kinds, "mem_mb": sum(KINDS[n.kind].mem_mb for n in topo.nodes.values()),
        "topology": topo.model_dump(),
    }
