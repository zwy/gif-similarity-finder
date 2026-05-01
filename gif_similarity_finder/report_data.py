from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ReportSummary:
    stage: str
    total_groups: int
    total_items: int
    grouped_items: int
    noise_items: int
    largest_group_size: int


@dataclass(slots=True)
class ReportGroup:
    group_id: str
    size: int
    is_noise: bool
    preview_items: list[str]


@dataclass(slots=True)
class ReportItem:
    path: str
    name: str
    group_id: str
    is_noise: bool
    group_size: int


@dataclass(slots=True)
class ReportDataset:
    summary: ReportSummary
    groups: list[ReportGroup]
    items: list[ReportItem]


def build_report_dataset(groups: dict[int | str, list[str]], stage: str) -> ReportDataset:
    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (int(item[0]) == -1, -len(item[1]), int(item[0])),
    )
    group_rows: list[ReportGroup] = []
    item_rows: list[ReportItem] = []

    grouped_items = 0
    noise_items = 0
    largest_group_size = 0

    for raw_group_id, paths in ordered_groups:
        is_noise = int(raw_group_id) == -1
        size = len(paths)
        if is_noise:
            noise_items += size
        else:
            grouped_items += size
            largest_group_size = max(largest_group_size, size)

        group_rows.append(
            ReportGroup(
                group_id=str(raw_group_id),
                size=size,
                is_noise=is_noise,
                preview_items=paths[:12],
            )
        )

        for path in paths:
            item_rows.append(
                ReportItem(
                    path=path,
                    name=Path(path).name,
                    group_id=str(raw_group_id),
                    is_noise=is_noise,
                    group_size=size,
                )
            )

    summary = ReportSummary(
        stage=stage,
        total_groups=len(group_rows),
        total_items=len(item_rows),
        grouped_items=grouped_items,
        noise_items=noise_items,
        largest_group_size=largest_group_size,
    )
    return ReportDataset(summary=summary, groups=group_rows, items=item_rows)
