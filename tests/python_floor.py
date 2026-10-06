from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import sys

DOWNLOADED = {"common", "logger", "main", "serial"}
FILTERED = {"extract", "extractall", "unpack_archive"}
FLOOR = (3, 9, 6)
FUNCTIONS = (ast.AsyncFunctionDef, ast.FunctionDef, ast.Lambda)
MISSING = object()
SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "dot_firmware.py"


def attributes(
    *, modules: dict[str, object], tree: ast.Module
) -> list[tuple[int, str]]:
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    found = []
    for node in ast.walk(tree):
        names = chain(node) if outermost(node, parents) else []
        if names and not isinstance(node.ctx, ast.Load):
            names = names[:-1]
        if names and names[0] in modules and not shadowed(names[0], node, parents):
            target = modules[names[0]]
            for name in names[1:]:
                if not hasattr(target, name):
                    found.append((node.lineno, ".".join(names)))
                    break
                target = getattr(target, name)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in FILTERED
            and any(keyword.arg == "filter" for keyword in node.keywords)
        ):
            found.append((node.lineno, node.func.attr + "(filter=...)"))
    return found


def bound(function: ast.AsyncFunctionDef | ast.FunctionDef | ast.Lambda) -> set[str]:
    arguments = function.args
    names = {
        argument.arg
        for argument in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            arguments.vararg,
            arguments.kwarg,
        )
        if argument
    }
    declared = set()
    pending = list(ast.iter_child_nodes(function))
    while pending:
        node = pending.pop()
        if isinstance(node, FUNCTIONS):
            names.update([] if isinstance(node, ast.Lambda) else [node.name])
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            declared.update(node.names)
        pending.extend(ast.iter_child_nodes(node))
    return names - declared


def chain(node: ast.expr) -> list[str]:
    names = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return []
    names.append(node.id)
    return names[::-1]


def imports(tree: ast.Module) -> tuple[dict[str, object], list[tuple[int, str]]]:
    modules = {}
    found = []
    for node in ast.walk(tree):
        aliases = node.names if isinstance(node, (ast.Import, ast.ImportFrom)) else []
        for alias in aliases:
            module = getattr(node, "module", None) or alias.name
            if module.split(".")[0] in DOWNLOADED:
                continue
            loaded = load(module)
            if loaded is None:
                found.append((node.lineno, "import " + module))
            elif isinstance(node, ast.Import):
                name = alias.asname or module.split(".")[0]
                modules[name] = loaded if alias.asname else load(name)
            elif alias.name != "*":
                value = member(loaded=loaded, module=module, name=alias.name)
                if value is MISSING:
                    found.append((node.lineno, f"from {module} import {alias.name}"))
                elif inspect.ismodule(value) or inspect.isclass(value):
                    modules[alias.asname or alias.name] = value
    return modules, found


def load(module: str) -> object:
    try:
        return importlib.import_module(module)
    except ImportError:
        return None


def main() -> int:
    if sys.version_info[:3] != FLOOR:
        print(f"Python {sys.version.split()[0]} is not the floor, 3.9.6")
        return 1
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    modules, found = imports(tree)
    found += attributes(modules=modules, tree=tree)
    for line, name in sorted(found):
        print(f"dot_firmware.py:{line}: {name} is not in Python 3.9.6")
    return 1 if found else 0


def member(*, loaded: object, module: str, name: str) -> object:
    if hasattr(loaded, name):
        return getattr(loaded, name)
    return load(f"{module}.{name}") or MISSING


def outermost(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    return isinstance(node, ast.Attribute) and not (
        isinstance(parent, ast.Attribute) and parent.value is node
    )


def shadowed(name: str, node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    while node in parents:
        node = parents[node]
        if isinstance(node, FUNCTIONS) and name in bound(node):
            return True
    return False


if __name__ == "__main__":
    sys.exit(main())
