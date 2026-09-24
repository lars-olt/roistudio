import unittest

from utils.scene_camera import display_camera


class DisplayCameraTests(unittest.TestCase):
    def test_prefers_instrument_default_when_both_eyes_exist(self):
        for instrument, eye in (('ZCAM', 'right'), ('PCAM', 'left')):
            self.assertEqual(display_camera({
                'instrument': instrument, 'left_band_keys': ['L1'], 'right_band_keys': ['R1'],
            }), eye)

    def test_selects_only_available_eye_for_both_instruments(self):
        for instrument in ('ZCAM', 'PCAM'):
            for eye in ('left', 'right'):
                with self.subTest(instrument=instrument, eye=eye):
                    self.assertEqual(display_camera({
                        'instrument': instrument,
                        'left_band_keys': ['L0B', 'L0G', 'L0R'] if eye == 'left' else [],
                        'right_band_keys': ['R0B', 'R0G', 'R0R'] if eye == 'right' else [],
                    }), eye)


if __name__ == '__main__':
    unittest.main()
