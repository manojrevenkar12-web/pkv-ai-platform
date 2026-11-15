import tomllib
from pathlib import Path

import numpy as np

from pkvai.usecases.assist import ClauseIndex, Embedder, grounded
from pkvai.usecases.invoices import ReadLine, mismatched, needs_reason, settle
from pkvai.usecases.routing import Router

FEES = tomllib.loads((Path(__file__).resolve().parents[1] / "config" / "fees.toml").read_text())
PV = FEES["point_value_eur"]


def line(code, factor, reason=False, agreement=False, count=1, amount=None):
    pts = FEES["codes"][code]["points"]
    return ReadLine(code, factor, round(pts * PV * factor * count, 2) if amount is None else amount, reason, agreement, count)


def test_above_the_threshold_without_a_reason_is_paid_at_the_threshold():
    s = settle([line("3", 3.5)], FEES)
    assert s.payable == round(150 * PV * 2.3, 2)
    assert "without a written reason" in s.notes[0]


def test_a_written_reason_keeps_the_factor():
    assert settle([line("3", 3.5, reason=True)], FEES).payable == round(150 * PV * 3.5, 2)


def test_above_the_maximum_needs_a_fee_agreement():
    assert settle([line("7", 4.5, reason=True)], FEES).payable == round(160 * PV * 3.5, 2)
    assert settle([line("7", 4.5, reason=True, agreement=True)], FEES).payable == round(160 * PV * 4.5, 2)


def test_pairs_that_exclude_each_other_drop_the_smaller_one():
    s = settle([line("1", 2.3), line("3", 2.3)], FEES)
    assert s.payable == round(150 * PV * 2.3, 2)
    assert "may not be billed" in s.notes[0]


def test_never_more_than_the_doctor_billed_and_counts_multiply():
    assert settle([line("410", 1.8, count=4, amount=10.0)], FEES).payable == 10.0
    assert settle([line("410", 1.8, count=4)], FEES).payable == round(200 * PV * 1.8 * 4, 2)


def test_the_self_check_finds_misreadings_and_missing_reasons():
    ok, bad = line("5", 2.3), line("5", 2.3, amount=99.0)
    assert mismatched([ok, bad], FEES) == [1]
    assert needs_reason([line("5", 3.0), line("5", 3.0, reason=True)], FEES) == [0]


def test_router_learns_and_notices_new_words():
    texts = ["rechnung erstattung arzt"] * 20 + ["beitrag lastschrift abbuchung"] * 20
    labels = ["leistung"] * 20 + ["beitrag"] * 20
    r = Router(["leistung", "beitrag"], 1024, 200, 20.0, 1e-5).fit(texts, labels)
    teams, conf = r.predict(["erstattung der rechnung", "lastschrift beitrag"])
    assert teams == ["leistung", "beitrag"] and (conf > 0.8).all()
    assert r.unknown_share(["völlig neue wörter hier"])[0] > 0.9
    warm = Router(["leistung", "beitrag"], 1024, 200, 20.0, 1e-5).fit(texts, labels, warm=r, epochs=5)
    assert warm.predict(["erstattung der rechnung"])[0] == ["leistung"]


def test_retrieval_and_the_grounding_check():
    clauses = [("X1", "Sehhilfen", "Brillen werden mit 300 Euro erstattet."), ("X2", "Selbstbehalt", "Der Selbstbehalt beträgt 600 Euro.")]
    idx = ClauseIndex(clauses, Embedder(256))
    assert idx.search("Wie hoch ist der Selbstbehalt?", 1)[0][0] == "X2"
    assert grounded(["X2"], "600 Euro", ["X2"], idx.text)
    assert not grounded(["X2"], "500 Euro", ["X2"], idx.text)  # states what the clause does not say
    assert not grounded(["X1"], "300 Euro", ["X2"], idx.text)  # cites a clause it was not given
    assert not grounded([], None, ["X2"], idx.text)
    assert np.isclose(np.linalg.norm(Embedder(64)("abc")), 1.0)
