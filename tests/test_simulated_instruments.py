"""
Tests for core/instruments/simulated.py's SimulatedMonochromator.shutter()/
shuttered -- must match Cornerstone130's real-driver signature/semantics
(close=True closes it) exactly, since mainwindow_qt.py's manual Shutter
control (and anything else) calls shutter(close=...) by keyword on
whichever monochromator is actually connected, real or simulated.

shutter() previously took a differently-named, oppositely-meant `open_`
parameter here -- harmless under the only calling pattern that existed
until now (a bare positional bool reads the same either way), but would
have silently inverted the shutter state under a keyword call.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eqe.core.instruments.simulated import SimulatedMonochromator


class SimulatedMonochromatorShutterTests(unittest.TestCase):
    def test_starts_shuttered(self):
        # __init__ sets shutter_open = False (closed), unchanged by this
        # fix -- shutter_open itself is never read by the simulated
        # current-generation model, so this default has no functional
        # effect either way, but shuttered should still report it
        # accurately.
        mono = SimulatedMonochromator()
        self.assertTrue(mono.shuttered)

    def test_shutter_close_true_closes_it(self):
        mono = SimulatedMonochromator()
        mono.shutter(close=True)
        self.assertTrue(mono.shuttered)

    def test_shutter_close_false_opens_it(self):
        mono = SimulatedMonochromator()
        mono.shutter(close=True)
        mono.shutter(close=False)
        self.assertFalse(mono.shuttered)

    def test_default_argument_closes_it(self):
        # Matches Cornerstone130.shutter()'s close: bool = True default.
        mono = SimulatedMonochromator()
        mono.shutter()
        self.assertTrue(mono.shuttered)

    def test_positional_bool_still_works(self):
        mono = SimulatedMonochromator()
        mono.shutter(True)
        self.assertTrue(mono.shuttered)
        mono.shutter(False)
        self.assertFalse(mono.shuttered)


if __name__ == "__main__":
    unittest.main()
