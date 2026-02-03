from .mcp.server.fastapi import MCPServer
from .tools_fs import list_dir, read_file, write_file

server = MCPServer(
    name="senteniel-mcp-sandbox",
    description="Sandboxed filesystem tools for Senteniel"
)

server.add_tool(
    name="fs.list_dir",
    description="List directory contents (sandboxed)",
    handler=list_dir,
)

server.add_tool(
    name="fs.read_file",
    description="Read a file (sandboxed, secrets blocked)",
    handler=read_file,
)

server.add_tool(
    name="fs.write_file",
    description="Write a file (sandboxed)",
    handler=write_file,
)

app = server.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7001)
