from __future__ import annotations

import ast
import functools
import inspect
import textwrap
from typing import TYPE_CHECKING

import pytest

from firebreak import cache, plan, route, unlock, updates
from firebreak.devices import BISCUIT, RADAR, TARGETS, biscuit, radar

if TYPE_CHECKING:
    from collections.abc import Callable

    from firebreak.plugin import Device

AMONET_LKS = {
    BISCUIT: (biscuit.V2_0_1_SOURCE, biscuit.V1_1_0_SOURCE),
    RADAR: (radar.SOURCE,),
}
EVERY_TARGET = [
    (device, name) for device, targets in TARGETS.items() for name in sorted(targets)
]
PURE = (
    ast.Attribute,
    ast.BoolOp,
    ast.Compare,
    ast.Constant,
    ast.IfExp,
    ast.Load,
    ast.Name,
    ast.Subscript,
    ast.Tuple,
    ast.UnaryOp,
    ast.boolop,
    ast.cmpop,
    ast.unaryop,
)

TARGET_IDS = [f"{device.name}-{name}" for device, name in EVERY_TARGET]
UNRESOLVED = object()


class Scan:
    def __init__(self) -> None:
        self.found: set[object] = set()
        self.maybe: set[object] = set()
        self.seen: set[tuple[object, ...]] = set()

    def call(self, *, node: ast.Call, scope: dict[str, object]) -> None:
        callee = value_of(node=node.func, scope=scope)
        keywords = {
            keyword.arg: value_of(node=keyword.value, scope=scope)
            for keyword in node.keywords
            if keyword.arg
        }
        if callee is cache.fetch or callee is cache.unpack:
            download = keywords.get("download", UNRESOLVED)
            assert download is not UNRESOLVED, ast.unparse(node)
            self.found.add(download)
        elif callee is updates.download:
            self.found.add(route.ota_build)
        else:
            self.function(
                bound={
                    name: value
                    for name, value in keywords.items()
                    if value is not UNRESOLVED
                },
                function=callee,
            )

    def calls(self, *, node: ast.AST, scope: dict[str, object]) -> None:
        for found in ast.walk(node):
            if isinstance(found, ast.Call):
                self.call(node=found, scope=scope)

    def function(self, *, bound: dict[str, object], function: object) -> None:
        if isinstance(function, functools.partial):
            for value in function.keywords.values():
                self.function(bound={}, function=value)
            self.function(bound=function.keywords | bound, function=function.func)
            return
        if function is plan.image_of:
            self.found |= set(bound["unlock"].files.values())
            return
        if function is unlock.fastbrick_payload:
            unlocking = bound["unlock"]
            self.found.add(unlocking.source)
            self.maybe |= set(unlocking.payloads.values())
            return
        if function is unlock.amonet_lk:
            first, *rest = AMONET_LKS[route.ARGUMENTS.target.device]
            self.found.add(first)
            self.maybe |= set(rest)
            return
        if not inspect.isfunction(function) or not function.__module__.startswith(
            "firebreak"
        ):
            return
        key = (function, *sorted((name, id(value)) for name, value in bound.items()))
        if key in self.seen:
            return
        self.seen.add(key)
        tree = ast.parse(textwrap.dedent(inspect.getsource(function))).body[0]
        assert isinstance(tree, ast.FunctionDef)
        self.statements(body=tree.body, scope={**function.__globals__, **bound})

    def statements(self, *, body: list[ast.stmt], scope: dict[str, object]) -> None:
        scope = dict(scope)
        for statement in body:
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                held = value_of(node=statement.value, scope=scope)
                if held is not UNRESOLVED:
                    scope[statement.targets[0].id] = held
            if isinstance(statement, ast.If):
                self.calls(node=statement.test, scope=scope)
                held = value_of(node=statement.test, scope=scope)
                if held is UNRESOLVED or held:
                    self.statements(body=statement.body, scope=scope)
                if held is UNRESOLVED or not held:
                    self.statements(body=statement.orelse, scope=scope)
                continue
            if isinstance(statement, ast.For):
                self.calls(node=statement.iter, scope=scope)
                values = value_of(node=statement.iter, scope=scope)
                if isinstance(statement.target, ast.Name) and isinstance(values, tuple):
                    for value in values:
                        self.statements(
                            body=statement.body,
                            scope={**scope, statement.target.id: value},
                        )
                    continue
            self.calls(node=statement, scope=scope)


def scanned(*, run: Callable[..., object]) -> Scan:
    scan = Scan()
    scan.function(bound={}, function=run)
    return scan


@pytest.mark.parametrize(("device", "name"), EVERY_TARGET, ids=TARGET_IDS)
def test_each_stage_needs_what_its_code_downloads(
    *, device: Device, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[device][name]
    )
    for state, stage in route.stages().items():
        needs: set[object] = set()
        for need in stage.needs:
            needs |= (
                {need} if isinstance(need, cache.Download) else scanned(run=need).found
            )
        scan = scanned(run=stage.run)
        assert scan.found <= needs <= scan.found | scan.maybe, state


@pytest.mark.parametrize(("device", "name"), EVERY_TARGET, ids=TARGET_IDS)
def test_every_need_a_stage_declares_can_be_called(
    *, device: Device, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[device][name]
    )
    monkeypatch.setattr(name="download", target=route.updates, value=lambda **_: None)
    monkeypatch.setattr(name="fetch", target=cache, value=lambda **_: None)
    monkeypatch.setattr(name="unpack", target=route, value=lambda **_: None)
    monkeypatch.setattr(name="pyserial_wheel", target=route, value=lambda: None)
    for state, stage in route.stages().items():
        for need in stage.needs:
            if not isinstance(need, cache.Download):
                assert need() is None, state


def value_of(*, node: ast.expr, scope: dict[str, object]) -> object:
    if not all(isinstance(part, PURE) for part in ast.walk(node)):
        return UNRESOLVED
    try:
        return eval(  # ruff: ignore[suspicious-eval-usage]
            compile(ast.Expression(body=node), filename="<scan>", mode="eval"),
            dict(scope),
        )
    except Exception:  # ruff: ignore[blind-except]
        return UNRESOLVED
