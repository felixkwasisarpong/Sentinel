// Tools
MERGE (t1:Tool {name:"fs.list_dir"})
MERGE (t2:Tool {name:"fs.read_file"})

// Controls
MERGE (c1:Control {id:"C-SANDBOX-BOUNDARY", name:"Sandbox Boundary", description:"Filesystem paths must remain under /sandbox"})

// Policies
MERGE (p1:Policy {id:"P-SANDBOX-001", title:"Sandbox-only filesystem", severity:"high",
  text:"Filesystem tools must only access paths under /sandbox. Any other path is blocked."})

// Incidents
MERGE (i1:Incident {id:"I-EXFIL-001", title:"Attempted secret exfil", severity:"high",
  summary:"Agent attempted to read /etc/passwd or other host secrets via tool calls."})

// Relationships
MERGE (p1)-[:APPLIES_TO]->(t1)
MERGE (p1)-[:APPLIES_TO]->(t2)
MERGE (p1)-[:MITIGATED_BY]->(c1)
MERGE (i1)-[:INVOLVED_TOOL]->(t2)
MERGE (i1)-[:RELATED_TO_POLICY]->(p1)