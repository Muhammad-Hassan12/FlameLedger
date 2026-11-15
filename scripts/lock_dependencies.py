"""Capture installed application dependency closures separately from builder/test packages."""
from importlib import metadata

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from scripts.common import ROOT


def closure(names):
    visited={}
    def visit(name):
        key=canonicalize_name(name)
        if key in visited:return
        dist=metadata.distribution(name)
        visited[key]=f"{dist.metadata['Name']}=={dist.version}"
        for text in dist.requires or []:
            requirement=Requirement(text)
            if requirement.marker is None or requirement.marker.evaluate({**default_environment(),"extra":""}):
                visit(requirement.name)
    for name in names:visit(name)
    return visited


def main():
    runtime=closure(["fastapi","uvicorn","httpx","numpy","pydantic","python-dotenv"])
    serving=closure([*runtime,"torch","transformers","sentence-transformers","safetensors"])
    note="# Captured from the tested Windows Python 3.12 environment; validate Linux resolution on the target host.\n"
    (ROOT/"requirements-runtime.lock").write_text(note+"\n".join(runtime[k] for k in sorted(runtime))+"\n",encoding="utf-8")
    (ROOT/"requirements-serving.lock").write_text(note+"# Install CPU torch from its official CPU index before this lock.\n-r requirements-runtime.lock\n"+"\n".join(serving[k] for k in sorted(serving) if k not in runtime)+"\n",encoding="utf-8")
    print(f"Pinned runtime: {len(runtime)} packages; live serving: {len(serving)} packages; no builder-only vision dependency.")


if __name__ == "__main__":main()
