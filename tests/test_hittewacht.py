"""De hittewacht: een zware run pauzeert zodra de Mac warm wordt, en gaat pas
verder als hij een tijdje koel blijft (PO 2026-10-21: "zorg erin dat de GPU
en CPU niet overhitten")."""

from doublecheck import hittewacht


def test_a_nominal_machine_keeps_running():
    assert hittewacht.beslis(0, gepauzeerd=False, koel_op_rij=0) == ("door", 0)


def test_a_warm_machine_pauses_the_run():
    for toestand in (1, 2, 3):
        assert hittewacht.beslis(toestand, gepauzeerd=False, koel_op_rij=0) == ("pauzeer", 0)


def test_a_paused_run_resumes_only_after_the_machine_stays_cool():
    actie, koel = hittewacht.beslis(0, gepauzeerd=True, koel_op_rij=0)
    assert actie == "wacht"
    actie, koel = hittewacht.beslis(0, gepauzeerd=True, koel_op_rij=koel)
    assert (actie, koel) == ("hervat", 0)


def test_a_warm_reading_while_paused_starts_the_cool_count_over():
    _, koel = hittewacht.beslis(0, gepauzeerd=True, koel_op_rij=0)
    assert hittewacht.beslis(1, gepauzeerd=True, koel_op_rij=koel) == ("wacht", 0)


def test_the_thermal_states_have_names_for_the_log():
    assert [hittewacht.naam(t) for t in range(4)] == ["nominaal", "licht verhoogd", "ernstig", "kritiek"]
    assert hittewacht.naam(9) == "onbekend (9)"
