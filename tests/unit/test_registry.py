"""Component registration (Section 15.1): duplicate rejection, manifest, isolated test
registries."""

from __future__ import annotations

import pytest

from inventory_optimizer.components.decorators import problem_family, solver_backend
from inventory_optimizer.components.registry import ComponentKind, Registry
from inventory_optimizer.domain.enums import Capability, Formulation
from inventory_optimizer.exceptions import RegistrationError


def test_default_registry_has_the_baseline_problem_family() -> None:
    import inventory_optimizer.components as components

    registration = components.default_registry.get(
        ComponentKind.PROBLEM_FAMILY, "securities_lending_inventory", "1"
    )
    assert registration.component_class.__name__ == "SecuritiesLendingInventoryProblem"
    assert registration.metadata["supported_formulations"] == frozenset(
        {Formulation.LP, Formulation.MIP, Formulation.QP}
    )


def test_duplicate_registration_is_rejected() -> None:
    registry = Registry()

    @solver_backend(name="fake", capabilities={Capability.LP}, registry=registry)
    class FakeBackend:
        capabilities = frozenset({Capability.LP})

        def solve(self, problem, options, warm_start=None):  # noqa: ANN001, ANN201
            raise NotImplementedError

    with pytest.raises(RegistrationError):

        @solver_backend(name="fake", capabilities={Capability.LP}, registry=registry)
        class FakeBackendAgain:
            capabilities = frozenset({Capability.LP})

            def solve(self, problem, options, warm_start=None):  # noqa: ANN001, ANN201
                raise NotImplementedError


def test_missing_required_attribute_is_rejected() -> None:
    registry = Registry()

    with pytest.raises(RegistrationError):

        @problem_family(
            name="incomplete",
            version="1",
            supported_formulations={Formulation.LP},
            registry=registry,
        )
        class IncompleteFamily:
            request_type = object
            # result_type intentionally missing


def test_isolated_registry_does_not_affect_default_registry() -> None:
    import inventory_optimizer.components as components

    isolated = Registry()

    @solver_backend(name="only_in_isolated", capabilities={Capability.LP}, registry=isolated)
    class IsolatedBackend:
        capabilities = frozenset({Capability.LP})

        def solve(self, problem, options, warm_start=None):  # noqa: ANN001, ANN201
            raise NotImplementedError

    with pytest.raises(RegistrationError):
        components.default_registry.get(ComponentKind.SOLVER_BACKEND, "only_in_isolated", "1")


def test_manifest_exposes_every_registration() -> None:
    registry = Registry()

    @solver_backend(name="manifest_test", capabilities={Capability.LP}, registry=registry)
    class ManifestTestBackend:
        capabilities = frozenset({Capability.LP})

        def solve(self, problem, options, warm_start=None):  # noqa: ANN001, ANN201
            raise NotImplementedError

    manifest = registry.manifest()
    assert len(manifest) == 1
    assert manifest[0].name == "manifest_test"
    assert manifest[0].kind == ComponentKind.SOLVER_BACKEND
