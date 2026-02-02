import os
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "testpassword")

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver

def fetch_policy_context(tool_name: str, args: dict) -> dict:
    """
    Option A: deterministic GraphRAG.
    Returns IDs only (citations), no LLM summarization.
    """
    path = str(args.get("path", "")) if args else ""
    driver = get_driver()

    with driver.session() as session:
        # Policies that apply to tool
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

        # If requested path is out of sandbox, attach related incidents
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