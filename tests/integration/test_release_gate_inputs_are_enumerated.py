# -*- coding: utf-8 -*-
"""Every required input a release gate declares is an input the standard enumerates.

The failure this exists for already happened. `369e585` made `--junit` mandatory on
`check_tag_gate.py`; the release-process standard kept listing three inputs, and
for about a day anyone who worked from the standard hit an argparse error before a
single check ran. The mismatch was found by hand, by a person reading both, and a
hand-found mismatch is found once: nothing went red, so nothing kept it from
recurring with the next required input.

The direction is deliberate and only one way: **script required ⊆ enumerated**.
Enumerating an input a script does not (yet) require is fine -- that is a standard
describing an input that is optional or planned. Requiring an input nobody
enumerated is the defect, because it turns a documented procedure into one that
fails at step zero.

``scripts/release_gate_inputs.json`` is the repository-side copy the check reads.
It cannot see the standard itself, which is maintained outside this repository, so
what is proven here is "the scripts agree with the copy" and not "the copy agrees
with the standard". That second half is a review question; please do not describe
this gate as if it covered it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
MANIFEST = SCRIPTS / "release_gate_inputs.json"


def declared_required(script: Path) -> set[str]:
    """The option strings this script marks ``required=True``.

    Read from the syntax tree rather than by running ``--help``: importing a gate
    script to ask it a question would execute whatever sits at module import, and
    a check that runs the thing it audits cannot be trusted to be neutral.
    """
    tree = ast.parse(script.read_text(encoding="utf-8"))
    required: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
            continue
        is_required = any(
            keyword.arg == "required"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )
        if not is_required:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith("--"):
                    required.add(arg.value)
    return required


def gate_scripts() -> dict[str, set[str]]:
    return {
        path.name: declared_required(path)
        for path in sorted(SCRIPTS.glob("check_*.py"))
    }


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def unenumerated_inputs(required_by_script: dict, enumerated: dict) -> list:
    """The decision, as a pure function so it can be replayed against history.

    Kept separate from the test that feeds it the live tree: a check that can only
    be exercised by editing the tree is a check whose "it would have caught that"
    claim nobody can test. This one is handed two mappings and answers.
    """
    problems = []
    for name in sorted(required_by_script):
        required = set(required_by_script[name])
        if not required:
            continue
        listed = set(enumerated.get(name, ()))
        missing = sorted(required - listed)
        if missing:
            problems.append(
                f"{name}: requires {missing} but scripts/release_gate_inputs.json "
                f"enumerates {sorted(listed) or '[]'}"
            )
    return problems


def test_every_required_input_is_enumerated_for_its_script():
    """The gate itself: a required input missing from the enumeration is red."""
    problems = unenumerated_inputs(gate_scripts(), manifest()["scripts"])
    assert not problems, (
        "a gate requires an input the release inputs manifest does not enumerate. "
        "Adding a required input changes the release process's input surface: list it "
        "here in this commit, and update the standard in the same round.\n  "
        + "\n  ".join(problems)
    )


def test_the_gate_would_have_caught_the_junit_change():
    """Replay the case this gate exists for, so it is not merely green today.

    `369e585` made `--junit` mandatory on the tag gate. At that moment the script
    required four inputs and the enumeration still listed three -- the shape below.
    Nobody's check went red, so the mismatch was found by a person reading both, a
    day later, and only for that one input.

    A check that passes on the current tree has shown nothing about whether it would
    have passed then. This feeds the historical shape to the same decision and
    requires it to name the missing input, so the "would have caught it" claim is
    itself tested -- and a decision that stops deciding fails here first: with the
    comparison neutered, this case is the only one that goes red.
    """
    as_it_was = {
        "check_tag_gate.py": {
            "--sign-off-token",
            "--review-token",
            "--sync-token",
            "--junit",  # made required by 369e585
        }
    }
    enumeration_as_it_was = {
        "check_tag_gate.py": ["--sign-off-token", "--review-token", "--sync-token"],
    }

    problems = unenumerated_inputs(as_it_was, enumeration_as_it_was)

    assert problems, (
        "the decision passed the historical shape, so it would not have caught the "
        "mismatch it was written for"
    )
    assert "'--junit'" in problems[0], (
        f"it went red, but not on the input that was actually added: {problems[0]}"
    )
    assert len(problems) == 1, f"one input was missing; reported {len(problems)}: {problems}"


def test_the_current_tree_has_no_difference():
    """The other half of the replay: today's answer is empty, and that is a fact.

    Stated as an assertion rather than left implicit, because "the diff is empty" is
    the reading the delivery claim rests on, and a future non-empty diff should break
    this line before it reaches a release note.
    """
    problems = unenumerated_inputs(gate_scripts(), manifest()["scripts"])
    assert problems == [], f"the current tree already has an unenumerated input: {problems}"


def test_the_manifest_describes_scripts_that_exist():
    """A stale entry hides the case it was written for, so it is red as well."""
    enumerated = manifest()["scripts"]
    present = set(gate_scripts())
    stale = sorted(set(enumerated) - present)
    assert not stale, (
        f"scripts/release_gate_inputs.json enumerates {stale}, which are not gate "
        "scripts in this tree; remove the entry or restore the script"
    )


def test_the_tag_gate_is_read_and_not_assumed_empty():
    """A guard against the check passing because it saw nothing.

    ``script required ⊆ enumerated`` is vacuously true when the script declares
    nothing, so the one script known to declare inputs has to be visible here --
    otherwise deleting its ``required=True`` markers would read as a pass.
    """
    declared = gate_scripts()
    assert "check_tag_gate.py" in declared, "the tag gate script was not found at all"
    assert declared["check_tag_gate.py"], (
        "check_tag_gate.py declares no required input any more; if that is deliberate "
        "it is a change to the release process and this check cannot be silent about it"
    )
    assert declared["check_tag_gate.py"] == set(
        manifest()["scripts"]["check_tag_gate.py"]
    ), (
        "the tag gate's required inputs and the manifest disagree in the other "
        "direction: "
        f"script={sorted(declared['check_tag_gate.py'])} "
        f"manifest={sorted(manifest()['scripts']['check_tag_gate.py'])}"
    )
