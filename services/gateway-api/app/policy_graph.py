from __future__ import annotations

import os
from functools import lru_cache

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "testpassword")

CYPHER_IDS = """
MATCH (p:Policy)-[:REFERS_TO]->(t:ToolContract {tool_name:$tool})
OPTIONAL MATCH (p)-[:ENFORCES]->(c:Control)
OPTIONAL MATCH (i:Incident)-[:VIOLATED_BY]->(p)
RETURN collect(DISTINCT p.id) AS policies,
       collect(DISTINCT i.id) AS incidents,
       collect(DISTINCT c.id) AS controls
"""


@lru_cache(maxsize=1)
def _cached_driver():
    uri = os.getenv("NEO4J_URI")
    if not uri:
        return None
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "")
    return GraphDatabase.driver(uri, auth=(user, pwd))


def _schema_ready_for_citations(session) -> bool:
    """
    Skip citation lookup if policy graph schema has not been seeded yet.
    This avoids noisy Neo4j notifications about missing labels/relationships.
    """
    labels = set(session.run("CALL db.labels() YIELD label RETURN collect(label) AS labels").single()["labels"] or [])
    rels = set(
        session.run(
            "CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS rels"
        ).single()["rels"]
        or []
    )
    props = set(session.run("CALL db.propertyKeys() YIELD propertyKey RETURN collect(propertyKey) AS props").single()["props"] or [])

    required_labels = {"Policy", "ToolContract", "Control", "Incident"}
    required_rels = {"REFERS_TO", "ENFORCES", "VIOLATED_BY"}
    required_props = {"tool_name", "id"}
    return (
        required_labels.issubset(labels)
        and required_rels.issubset(rels)
        and required_props.issubset(props)
    )


def lookup_policy_ids(tool_name: str) -> tuple[list[str], list[str], list[str]]:
    drv = _cached_driver()
    if not drv:
        return [], [], []
    with drv.session() as session:
        if not _schema_ready_for_citations(session):
            return [], [], []
        rec = session.run(CYPHER_IDS, tool=tool_name).single()
        if not rec:
            return [], [], []
        policies = [x for x in rec["policies"] if x]
        incidents = [x for x in rec["incidents"] if x]
        controls = [x for x in rec["controls"] if x]
        return policies, incidents, controls


def get_driver():
    return _cached_driver()


def fetch_policy_context(tool_name: str, args: dict) -> dict:
    """
    Deterministic graph lookup used by some internal flows.
    Returns IDs only (citations), no LLM summarization.
    """
    path = str(args.get("path", "")) if args else ""
    driver = get_driver()
    if not driver:
        return {
            "policy_citations": [],
            "control_refs": [],
            "incident_refs": [],
        }

    with driver.session() as session:
        policies = session.run(
            """
            MATCH (p:Policy)-[:APPLIES_TO]->(t:Tool {name:$tool})
            RETURN p.id AS id
            """,
            tool=tool_name,
        ).value()

        controls = session.run(
            """
            MATCH (p:Policy)-[:APPLIES_TO]->(t:Tool {name:$tool})
            MATCH (p)-[:MITIGATED_BY]->(c:Control)
            RETURN DISTINCT c.id AS id
            """,
            tool=tool_name,
        ).value()

        incident_ids = []
        if tool_name in ("fs.read_file", "fs.list_dir") and path and not (path == "/sandbox" or path.startswith("/sandbox/")):
            incident_ids = session.run(
                """
                MATCH (i:Incident)-[:INVOLVED_TOOL]->(t:Tool {name:$tool})
                RETURN i.id AS id
                """,
                tool=tool_name,
            ).value()

    return {
        "policy_citations": policies or [],
        "control_refs": controls or [],
        "incident_refs": incident_ids or [],
    }
