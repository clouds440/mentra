import unittest
from pydantic import ValidationError
from app.chat.interactions import ValueBarsContent


class ComparisonContracts(unittest.TestCase):
    def test_groups_and_color_overrides_preserve_explicit_values(self):
        value = ValueBarsContent(question='Compare', bars=[
            dict(label='React', group='Animation', series='React', value=5, max=5, color='blue'),
            dict(label='Angular', group='Animation', series='Angular', value=3, max=5, color='red'),
        ])
        self.assertEqual([bar.value for bar in value.bars], [5, 3])
        self.assertEqual(value.bars[1].color, 'red')
        self.assertEqual(ValueBarsContent(question='Legacy', bars=[dict(label='Old', value=2, max=5)]).bars[0].group, '')

    def test_inconsistent_comparisons_and_unsafe_colors_are_rejected(self):
        base = dict(label='React', group='Animation', series='React', value=5, max=5)
        for other in [dict(base), dict(base, series='Angular', max=10), dict(base, series='Angular', unit='ms')]:
            with self.assertRaises(ValidationError): ValueBarsContent(question='Compare', bars=[base, other])
        for changed in [dict(base, color='url(https://bad.example)'), dict(base, series=''), dict(base, group='')]:
            with self.assertRaises(ValidationError): ValueBarsContent(question='Compare', bars=[changed])
        with self.assertRaises(ValidationError): ValueBarsContent(question='Compare', bars=[dict(base, color='blue'), dict(base, group='Forms', color='red')])
