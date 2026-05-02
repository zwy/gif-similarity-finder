from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
from typing import List

@dataclass(slots=True)
class DashboardSummary:
    total_items: int
    total_groups: int
    grouped_items: int
    noise_items: int
    largest_group_size: int

@dataclass(slots=True)
class DashboardItem:
    id: str
    name: str
    gif_path: str
    preview_path: str
    group_id: str
    group_size: int
    is_noise: bool
    stage: str

@dataclass(slots=True)
class DashboardStage:
    stage_key: str
    summary: DashboardSummary
    items: List[DashboardItem]

@dataclass(slots=True)
class DashboardShard:
    file_name: str
    items: List[DashboardItem]


def stable_item_id(gif_path: Path) -> str:
    # deterministic short id derived from the path string
    return hashlib.sha1(str(gif_path).encode("utf-8")).hexdigest()[:16]


def build_dashboard_stage(stage_key: str, groups: dict, preview_dir_name: str) -> DashboardStage:
    items: List[DashboardItem] = []
    for group_key, paths in groups.items():
        group_size = len(paths)
        try:
            is_noise_flag = int(group_key) == -1
        except Exception:
            is_noise_flag = False
        for p in paths:
            ppath = Path(p)
            sid = stable_item_id(ppath)
            preview = f"{preview_dir_name}/{sid}.webp"
            item = DashboardItem(
                id=sid,
                name=ppath.stem,
                gif_path=str(ppath),
                preview_path=preview,
                group_id=str(group_key),
                group_size=group_size,
                is_noise=is_noise_flag,
                stage=stage_key,
            )
            items.append(item)
    total_items = len(items)
    def _is_noise(k):
        try:
            return int(k) == -1
        except Exception:
            return False

    total_groups = sum(1 for k in groups.keys() if not _is_noise(k))
    grouped_items = sum(len(v) for k, v in groups.items() if not _is_noise(k))
    noise_items = sum(len(v) for k, v in groups.items() if _is_noise(k))
    largest_group_size = max((len(v) for k, v in groups.items() if not _is_noise(k)), default=0)
    summary = DashboardSummary(
        total_items=total_items,
        total_groups=total_groups,
        grouped_items=grouped_items,
        noise_items=noise_items,
        largest_group_size=largest_group_size,
    )
    return DashboardStage(stage_key=stage_key, summary=summary, items=items)


def split_stage_items(stage: DashboardStage, shard_size: int) -> list[DashboardShard]:
    if shard_size <= 0:
        raise ValueError("shard_size must be > 0")
    shards: list[DashboardShard] = []
    items = stage.items
    for i in range(0, len(items), shard_size):
        chunk = items[i : i + shard_size]
        idx = i // shard_size
        file_name = f"dashboard_{stage.stage_key}_{idx:03d}.js"
        shards.append(DashboardShard(file_name=file_name, items=chunk))
    return shards


def build_dashboard_manifest(output_dir: Path, stages: list[DashboardStage]) -> dict:
    manifest = {}
    for stage in stages:
        shards = split_stage_items(stage, shard_size=1000)
        manifest[stage.stage_key] = {
            "summary": asdict(stage.summary),
            "shards": [
                {
                    "file_name": s.file_name,
                    "size": len(s.items),
                    "path": str(Path(output_dir) / s.file_name),
                }
                for s in shards
            ],
        }
    return manifest
