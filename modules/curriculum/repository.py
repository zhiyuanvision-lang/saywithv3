from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

MAP_DIRECTORY = "research/long-term-map-model-review-2026-10-02"


class CurriculumRepository:
    """The map version and its references stay pinned for the object's lifetime.

    Reads research workspaces and exported workspaces with identical paths.
    Does not infer official scores, select legacy candidates or mutate data.
    """

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        self.directory = self.workspace / MAP_DIRECTORY
        self.map = json.loads((self.directory / "curriculum_map.json").read_text())
        self.targets = {g["id"]: g for g in self.map["learning_objectives"]}
        self.groups = {g["id"]: g for g in self.map["capability_groups"]}

    @property
    def version(self) -> str:
        return self.map["version"]

    def resolve(self, reference: str) -> Path:
        path = (self.directory / reference.split("#", 1)[0]).resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError("Reference escapes the curriculum workspace")
        return path

    def get_target(self, target_id: str) -> dict:
        """Only the current reviewed contract is a generation authority."""
        g = self.targets[target_id]
        return copy.deepcopy({
            "schema_version": "1.0", "map_version": self.version,
            "target_id": g["id"], "target_version": self.version,
            "parent_id": g["parent_id"], "outcome": g["outcome"],
            "reference_stage": g["reference_stage"],
            "generation_contract": g["generation_contract"],
            "assessment_check": g["assessment_check"],
            "reviewed_standard_references": g["reviewed_standard_references"],
            "language_resources": g["language_resources"],
            "clb_condition_source_ids": g["clb_condition_source_ids"],
            "learner_release_status": g["learner_release_status"],
        })

    def list_targets(self, *, stage: str | None = None, family: str | None = None) -> list[dict]:
        return [self.get_target(g["id"]) for g in self.targets.values()
                if (stage is None or g["reference_stage"] == stage)
                and (family is None or self.groups[g["parent_id"]]["family_id"] == family)]

    def query_senses(self, *, query: str, audiences: tuple[str, ...] = ("GL", "SSGL"),
                     limit: int = 20, excluded_ids: tuple[str, ...] = ()) -> list[dict]:
        """Candidate retrieval, never automatic teaching-resource approval.

        Matches literal text; excludes known sense IDs; ungraded and starred
        source status survives. Topics and task relevance need later filtering.
        """
        if not 1 <= limit <= 100 or not audiences:
            raise ValueError("limit must be 1..100 and audiences cannot be empty")
        path = self.resolve(self.map["lexicon"]["database"])
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where = "audience IN (" + ",".join("?" for _ in audiences) + ")"
        args = list(audiences)
        where += " AND expression LIKE ? ESCAPE '\\'"
        args.append("%" + escaped + "%")
        if excluded_ids:
            where += " AND id NOT IN (" + ",".join("?" for _ in excluded_ids) + ")"
            args.extend(excluded_ids)
        args.append(limit)
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                "SELECT id,expression,definition,example,gse,cefr,audience,gse_raw,gse_status "
                "FROM senses WHERE " + where + " ORDER BY expression,id LIMIT ?", args)]

    def validate(self) -> dict:
        checks: list[dict] = []
        def check(name: str, value: bool):
            checks.append({"name": name, "passed": bool(value)})
        check("unique_targets", len(self.targets) == len(self.map["learning_objectives"]))
        check("unique_groups", len(self.groups) == len(self.map["capability_groups"]))
        refs = json.loads(self.resolve(self.map["standard_reference_catalogs"]["gse_records"]).read_text())
        refs += json.loads(self.resolve(self.map["standard_reference_catalogs"]["gse_grammar"]).read_text())
        ref_ids = {id for r in refs for id in [r["id"]] + r.get("legacy_alias_ids", [])}
        for g in self.targets.values():
            check(g["id"] + ":parent", g["parent_id"] in self.groups)
            check(g["id"] + ":version", g["generation_contract"]["target_version"] == self.version)
            check(g["id"] + ":outcome", g["generation_contract"]["main_outcome"] == g["outcome"])
            for ref in g["reviewed_standard_references"]:
                check(g["id"] + ":reference", ref["reference_id"] in ref_ids and self.resolve(ref["source_file"]).is_file())
                check(g["id"] + ":reference_boundary", not ref["official_equivalence"] and not ref["learner_score_authority"])
        for name, ref in self.map["standard_reference_catalogs"].items():
            check("catalog:" + name, self.resolve(ref).is_file())
        check("oral_catalog", self.resolve(self.map["standard_goal_catalog"]).is_file())
        policy = json.loads(self.resolve(self.map["release_policy"]).read_text())
        check("backend_data_ready", policy["backend_data_ready"])
        check("map_not_full_course_launch", not policy["public_ready"])
        database = self.resolve(self.map["lexicon"]["database"])
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as conn:
            rows = conn.execute("SELECT COUNT(*) FROM senses").fetchone()[0]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        check("sense_count", rows == self.map["lexicon"]["rows"])
        check("sqlite_integrity", integrity == "ok")
        failed = [c["name"] for c in checks if not c["passed"]]
        return {"status": "failed" if failed else "passed", "map_version": self.version,
                "groups": len(self.groups), "targets": len(self.targets), "senses": rows,
                "checks": len(checks), "failed": failed,
                "scope": "data structure, references, runtime contracts and read-only resource integrity"}
