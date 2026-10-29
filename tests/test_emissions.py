"""Tests for the emission estimate. Run with:  python -m unittest"""

import unittest

import emissions
import ship_types


class ReferenceCase(unittest.TestCase):
    """8000 kW engine, design speed 14 knots, sailing at 10 knots."""

    def setUp(self):
        self.result = emissions.estimate_from_power(
            installed_kw=8000, design_speed=14, speed=10, aux_kw=500
        )

    def test_power(self):
        # 8000 * (10/14)^3 = 2915 kW
        self.assertAlmostEqual(self.result.main_kw, 2900, delta=50)
        self.assertEqual(self.result.aux_kw, 0)

    def test_fuel(self):
        # 2915 kW * 190 g/kWh = 554 kg/h
        self.assertAlmostEqual(self.result.fuel_kg_per_h, 550, delta=10)

    def test_co2(self):
        # 554 kg * 3.206 = 1776 kg/h, about 1.8 t
        self.assertAlmostEqual(self.result.co2_kg_per_h / 1000, 1.8, delta=0.05)


class LoadFactor(unittest.TestCase):
    def test_never_above_full_power(self):
        self.assertEqual(emissions.load_factor(speed=20, design_speed=14), 1.0)

    def test_lower_limit_at_low_speed(self):
        self.assertEqual(emissions.load_factor(speed=1.5, design_speed=14), emissions.MIN_LOAD)

    def test_propeller_law(self):
        self.assertAlmostEqual(emissions.load_factor(speed=7, design_speed=14), 0.125)


class Stationary(unittest.TestCase):
    def test_only_auxiliary_below_one_knot(self):
        result = emissions.estimate_from_power(
            installed_kw=8000, design_speed=14, speed=0.5, aux_kw=500
        )
        self.assertEqual(result.main_kw, 0)
        self.assertEqual(result.aux_kw, 500)
        # 500 kW * 220 g/kWh = 110 kg fuel, * 3.206 = 352.7 kg CO2
        self.assertAlmostEqual(result.fuel_kg_per_h, 110)
        self.assertAlmostEqual(result.co2_kg_per_h, 352.66)

    def test_one_knot_counts_as_moving(self):
        result = emissions.estimate_from_power(
            installed_kw=8000, design_speed=14, speed=1.0, aux_kw=500
        )
        self.assertGreater(result.main_kw, 0)
        self.assertEqual(result.aux_kw, 0)


class ShipLookup(unittest.TestCase):
    def test_power_grows_with_length(self):
        small = emissions.engine_profile("Lasteskip", 50)
        large = emissions.engine_profile("Lasteskip", 180)
        self.assertLess(small.main_kw, large.main_kw)

    def test_length_on_table_boundary(self):
        self.assertEqual(emissions.engine_profile("Lasteskip", 100).main_kw, 1_120)
        self.assertEqual(emissions.engine_profile("Lasteskip", 101).main_kw, 3_320)

    def test_small_vessels_use_own_estimate(self):
        small = emissions.engine_profile("Fiskefartøy", emissions.SMALL_VESSEL_LENGTH)
        self.assertNotIn("IMO", small.source)
        larger = emissions.engine_profile("Fiskefartøy", emissions.SMALL_VESSEL_LENGTH + 1)
        self.assertIn("IMO", larger.source)

    def test_unknown_length_uses_typical_length(self):
        typical = emissions.PROFILES["Lasteskip"]["typical_length"]
        self.assertEqual(
            emissions.engine_profile("Lasteskip", None),
            emissions.engine_profile("Lasteskip", typical),
        )

    def test_rows_sorted_by_length(self):
        for category, profile in emissions.PROFILES.items():
            lengths = [row.max_length for row in profile["rows"]]
            self.assertEqual(lengths, sorted(lengths), category)
            self.assertEqual(lengths[-1], emissions.INF, category)

    def test_cruise_ship_at_quay_uses_shore_power(self):
        at_quay = emissions.estimate_ship("Passasjerskip", 250, 0)
        self.assertTrue(at_quay.shore_power)
        self.assertEqual(at_quay.co2_kg_per_h, 0)
        sailing = emissions.estimate_ship("Passasjerskip", 250, 15)
        self.assertFalse(sailing.shore_power)
        self.assertGreater(sailing.co2_kg_per_h, 0)

    def test_ferry_at_quay_still_counts_auxiliary_engines(self):
        ferry = emissions.estimate_ship("Passasjerskip", 120, 0)
        self.assertFalse(ferry.shore_power)
        self.assertGreater(ferry.co2_kg_per_h, 0)

    def test_unknown_speed_gives_no_estimate(self):
        self.assertIsNone(emissions.estimate_ship("Lasteskip", 90, None))
        self.assertIsNone(emissions.estimate_ship("Lasteskip", 90, 102.3))

    def test_every_category_has_a_profile(self):
        self.assertEqual(set(emissions.PROFILES), set(ship_types.CATEGORIES))


if __name__ == "__main__":
    unittest.main()
