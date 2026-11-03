import unittest

import server
from backend.domain.requirements import local_interpret


class ModelValidationTests(unittest.TestCase):
    def test_valid_parametric_model_is_accepted(self):
        model = {
            "width": 10,
            "length": 20,
            "components": [
                {"id": "room-a", "name": "Sala", "type": "room", "x": -2, "z": -4, "w": 2, "d": 4, "h": .06, "y": .06},
                {"id": "room-b", "name": "Cocina", "type": "room", "x": 0, "z": -4, "w": 2, "d": 4, "h": .06, "y": .06},
            ],
        }
        self.assertEqual(server.validate_model(model), [])

    def test_component_outside_site_is_rejected(self):
        model = {"width": 10, "length": 20, "components": [{"id": "x", "name": "Casa", "type": "building", "x": 4, "z": 0, "w": 2, "d": 2, "h": 2, "y": 0}]}
        self.assertTrue(any("límites laterales" in issue for issue in server.validate_model(model)))

    def test_overlapping_rooms_are_rejected(self):
        rooms = [{"id": str(i), "name": f"Habitación {i}", "type": "room", "x": 0, "z": 0, "w": 3, "d": 3, "h": .06, "y": .06} for i in range(2)]
        self.assertTrue(any("se superponen" in issue for issue in server.validate_model({"width": 10, "length": 20, "components": rooms})))

    def test_non_numeric_geometry_is_reported_without_crash(self):
        component = {"id": "x", "name": "Casa", "type": "building", "x": "invalid", "z": 0, "w": 2, "d": 2, "h": 2, "y": 0}
        self.assertTrue(server.validate_model({"width": 10, "length": 20, "components": [component]}))


class OfflineRequirementsTests(unittest.TestCase):
    def test_sample_prompt_is_parsed_to_bounded_requirements(self):
        value = local_interpret("casa moderna de dos pisos sobre terreno 10 x 20 con tres dormitorios y dos baños")
        self.assertEqual((value["width"], value["length"], value["floors"], value["bedrooms"], value["baths"]), (10, 20, 2, 3, 2))

    def test_spanish_number_words_are_parsed(self):
        value = local_interpret("casa de dos niveles con cinco dormitorios y tres baños")
        self.assertEqual((value["floors"], value["bedrooms"], value["baths"]), (2, 5, 3))


if __name__ == "__main__":
    unittest.main()
