from django.test import TestCase

from listings.choices import PropertyTypes


class PropertyTypesTest(TestCase):
    def test_special_pretty_names(self):
        for propety_type in (
            PropertyTypes.Camper_Rv,
            PropertyTypes.Caravan_Mobile_Home,
            PropertyTypes.Ski_Inn,
        ):
            self.assertIn("/", propety_type.pretty_name)
