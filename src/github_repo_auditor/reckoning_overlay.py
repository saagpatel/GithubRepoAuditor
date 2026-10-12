"""Read-only private family verdicts; never part of canonical portfolio truth."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


class ReckoningOverlayError(ValueError):
    """An explicitly requested overlay could not be read or validated."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ReckoningOverlayError(
                f"Invalid YAML mapping key at line {key_node.start_mark.line + 1}"
            ) from exc
        if duplicate:
            raise ReckoningOverlayError(
                f"duplicate YAML mapping key at line {key_node.start_mark.line + 1}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _path_key(value: str, workspace_root: Path | None) -> str:
    # Normalize lexically: overlay validation must not read or resolve checkouts.
    path = posixpath.normpath(Path(value).expanduser().as_posix()).casefold()
    root = posixpath.normpath(
        (workspace_root or Path.home() / "Projects").expanduser().as_posix()
    ).casefold()
    if path.startswith(root + "/"):
        path = path[len(root) + 1 :]
    return path


@dataclass(frozen=True)
class ReckoningOverlay:
    # Retain the original mappings, including forward-compatible unknown fields.
    data: dict[str, Any]

    @property
    def families(self) -> dict[str, dict[str, Any]]:
        return self.data["families"]

    def lookup(
        self,
        *,
        github_id: int | None = None,
        repo_full_name: str = "",
        local_path: str = "",
        workspace_root: Path | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        """Match globally by ID, then owner/repo, then workspace-relative path."""
        matches = self.lookup_members(
            github_id=github_id,
            repo_full_name=repo_full_name,
            local_path=local_path,
            workspace_root=workspace_root,
        )
        if matches:
            family_id = matches[0][0]
            return family_id, self.families[family_id]
        return None

    def lookup_members(
        self,
        *,
        github_id: int | None = None,
        repo_full_name: str = "",
        local_path: str = "",
        workspace_root: Path | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Resolve the family by ID > name > path, then match its member aliases."""
        members = [
            (family_id, member)
            for family_id, family in self.families.items()
            for member in family["members"]
        ]
        matches: list[tuple[str, dict[str, Any]]] = []
        if github_id is not None:
            matches.extend(
                [
                    (family_id, member)
                    for family_id, member in members
                    if member.get("github_id") == github_id
                ]
            )
        if repo_full_name:
            matches.extend(
                [
                    (family_id, member)
                    for family_id, member in members
                    if member["key"].casefold() == repo_full_name.casefold()
                ]
            )
        if local_path:
            target = _path_key(local_path, workspace_root)
            matches.extend(
                [
                    (family_id, member)
                    for family_id, member in members
                    if any(
                        _path_key(path, workspace_root) == target
                        for path in [member["key"], *member.get("local_paths", [])]
                    )
                ]
            )
        if not matches:
            return []
        family_id = matches[0][0]
        matched_keys = {
            member["key"] for matched_id, member in matches if matched_id == family_id
        }
        return [
            (family_id, member)
            for matched_id, member in members
            if matched_id == family_id and member["key"] in matched_keys
        ]


def _validate(data: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(data, dict):
        raise ReckoningOverlayError("Invalid reckoning overlay: root must be a mapping")
    if data.get("schema") != "reckoning-verdicts/1":
        errors.append("schema must be reckoning-verdicts/1")
    _validate_timestamp(data.get("updated_at"), "updated_at", errors)
    families = data.get("families")
    if not isinstance(families, dict):
        errors.append("families must be a mapping")
        families = {}
    identities: dict[tuple[str, Any], str] = {}
    for family_id, family in families.items():
        prefix = f"families.{family_id}"
        if not isinstance(family_id, str) or not family_id.strip():
            errors.append("family IDs must be non-empty strings")
        if not isinstance(family, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        enums: dict[str, set[str | None]] = {
            "fate": {"keep", "archive", "assimilate", "pending"},
            "status": {"proposed", "approved", "executed"},
            "gut": {"love", "meh", "done", None},
        }
        for field, allowed in enums.items():
            value = family.get(field)
            if not isinstance(value, (str, type(None))) or value not in allowed:
                errors.append(f"{prefix}.{field} has an invalid value")
        for field in ("title", "cluster", "rationale", "assimilate_into"):
            if family.get(field) is not None and not isinstance(family[field], str):
                errors.append(f"{prefix}.{field} must be text or null")
        _validate_timestamp(family.get("decided_at"), f"{prefix}.decided_at", errors)
        if family.get("fate") == "assimilate":
            target = family.get("assimilate_into")
            if not isinstance(target, str) or target not in families:
                errors.append(
                    f"{prefix}.assimilate_into must reference an existing family"
                )
        tags = family.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            errors.append(f"{prefix}.tags must be a list of strings")
            tags = []
        evidence = family.get("evidence", {})
        if evidence is None:
            evidence = {}
        if not isinstance(evidence, dict):
            errors.append(f"{prefix}.evidence must be a mapping")
            evidence = {}
        for field in ("dossier", "biography", "seed_brief"):
            if evidence.get(field) is not None and not isinstance(evidence[field], str):
                errors.append(f"{prefix}.evidence.{field} must be text or null")
        if (
            "reborn-seed" in tags
            and family.get("status") in ("approved", "executed")
            and not evidence.get("seed_brief")
        ):
            errors.append(
                f"{prefix}.evidence.seed_brief is required for an approved reborn-seed"
            )
        github = family.get("github", {})
        if github is None:
            github = {}
        if not isinstance(github, dict):
            errors.append(f"{prefix}.github must be a mapping")
        elif github.get("visibility_after", "unchanged") not in (
            "unchanged",
            "public",
            "private",
        ):
            errors.append(f"{prefix}.github.visibility_after has an invalid value")
        if "wave" in family and (type(family["wave"]) is not int or family["wave"] < 0):
            errors.append(f"{prefix}.wave must be a non-negative integer")
        members = family.get("members")
        if not isinstance(members, list) or not members:
            errors.append(f"{prefix}.members must be a non-empty list")
            continue
        for index, member in enumerate(members):
            member_prefix = f"{prefix}.members[{index}]"
            if not isinstance(member, dict):
                errors.append(f"{member_prefix} must be a mapping")
                continue
            key = member.get("key")
            if not isinstance(key, str) or not key.strip():
                errors.append(f"{member_prefix}.key must be a non-empty string")
                continue
            member_ids: list[tuple[str, Any]] = [
                ("key", key.casefold()),
                ("path", _path_key(key, None)),
            ]
            github_id = member.get("github_id")
            if github_id is not None:
                if type(github_id) is not int or github_id <= 0:
                    errors.append(
                        f"{member_prefix}.github_id must be a positive integer"
                    )
                else:
                    member_ids.append(("github_id", github_id))
            paths = member.get("local_paths", [])
            if not isinstance(paths, list) or any(
                not isinstance(path, str) or not path for path in paths
            ):
                errors.append(
                    f"{member_prefix}.local_paths must be a list of non-empty strings"
                )
            else:
                member_ids.extend(("path", _path_key(path, None)) for path in paths)
            if member.get("role", "primary") not in (
                "primary",
                "mirror",
                "variant",
                "worktree",
                "leftover",
            ):
                errors.append(f"{member_prefix}.role has an invalid value")
            for identity in member_ids:
                previous = identities.get(identity)
                if previous is not None and previous != family_id:
                    errors.append(
                        f"{member_prefix}.{identity[0]} also appears in family {previous}"
                    )
                identities[identity] = family_id
    if errors:
        raise ReckoningOverlayError(
            "Invalid reckoning overlay:\n- " + "\n- ".join(errors)
        )
    return data


def _validate_timestamp(value: Any, field: str, errors: list[str]) -> None:
    if value is None or isinstance(value, datetime):
        return
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return
        except ValueError:
            pass
    errors.append(f"{field} must be an ISO timestamp or null")


def load_reckoning_overlay(path: Path | None = None) -> ReckoningOverlay | None:
    """Load an explicit overlay path; environment selection belongs to the CLI."""
    if path is None:
        return None
    overlay_path = path.expanduser()
    try:
        data = yaml.load(
            overlay_path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader
        )
    except (OSError, UnicodeError) as exc:
        raise ReckoningOverlayError(f"Cannot read reckoning overlay: {exc}") from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}" if mark else ""
        raise ReckoningOverlayError(
            f"Invalid reckoning overlay YAML{location}"
        ) from exc
    return ReckoningOverlay(_validate(data))
