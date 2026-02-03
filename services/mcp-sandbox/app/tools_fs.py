from pydantic import BaseModel
from pathlib import Path
from .sandbox import validate_path, is_secret

class ListDirArgs(BaseModel):
    path: str

class ReadFileArgs(BaseModel):
    path: str

def list_dir(path: str):
    args = ListDirArgs(path=path)
    path = validate_path(args.path)
    if not path.exists() or not path.is_dir():
        raise ValueError("Directory does not exist")

    return [p.name for p in path.iterdir()]

def read_file(path: str):
    args = ReadFileArgs(path=path)
    path = validate_path(args.path)

    if is_secret(path):
        raise ValueError("Access to secret files is denied")

    if not path.exists() or not path.is_file():
        raise ValueError("File does not exist")

    return path.read_text()


class WriteFileArgs(BaseModel):
    path: str
    content: str


def write_file(path: str, content: str):
    args = WriteFileArgs(path=path, content=content)
    path = validate_path(args.path)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args.content)
    return f"OK wrote {len(args.content.encode('utf-8'))} bytes"
