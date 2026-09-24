import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np


def _load_callbacks():
    settings = types.ModuleType('asdf_settings')
    settings.rapidlooks = SimpleNamespace(CROP_SETTINGS={'crop': (2, 3, 4, 5)})
    constants = types.ModuleType('sparc.core.constants')
    constants.get_instrument_config = lambda _instrument: {}
    spec = importlib.util.spec_from_file_location(
        'sparc_callbacks_under_test',
        Path(__file__).parents[1] / 'controllers' / 'sparc_callbacks.py',
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        'asdf_settings': settings, 'sparc.core.constants': constants,
    }):
        spec.loader.exec_module(module)
    return module


callbacks = _load_callbacks()


def full_scene(instrument='ZCAM'):
    image = np.arange(20 * 30).reshape(20, 30)
    cube = image[np.newaxis].copy()
    rgb = np.repeat(image[:, :, np.newaxis], 3, axis=2)
    return {
        'id': 'scene', 'instrument': instrument, 'sensor_crop': (0, 0, 0, 0),
        'cube': cube, 'left_cube': cube.copy(), 'right_cube': cube.copy(),
        'left_cube_aligned': cube.copy(), 'merged_band_recipe': [],
        'rgb_img': rgb, 'left_rgb_img': rgb.copy(), 'right_rgb_img': rgb.copy(),
        'homography_mask': image == -1, 'base_bands': {'R0': image.copy()},
        'homography_matrix': np.array([[1, .1, 3], [.2, 1, 2], [.001, .002, 1]]),
    }


class AlgorithmCoordinatesTests(unittest.TestCase):
    def test_default_margins_and_user_crop_intersect_in_full_image_coordinates(self):
        scene = full_scene()
        self.assertEqual(callbacks._algorithm_crop_rect(scene), (2, 4, 25, 11))
        self.assertEqual(callbacks._algorithm_crop_rect(scene, (0, 0, 10, 10)),
                         (2, 4, 8, 6))
        self.assertEqual(callbacks._algorithm_crop_rect(scene, (8, 6, 4, 3)),
                         (8, 6, 4, 3))
        with self.assertRaises(ValueError):
            callbacks._algorithm_crop_rect(scene, (0, 0, 2, 3))
        scene['instrument'] = 'PCAM'
        self.assertEqual(callbacks._algorithm_crop_rect(scene), (0, 0, 30, 20))
        self.assertEqual(callbacks._algorithm_crop_rect(scene, (1, 2, 4, 5)),
                         (1, 2, 4, 5))

    def test_algorithm_arrays_and_homography_use_crop_without_mutating_display(self):
        scene = full_scene()
        cropped = callbacks._apply_crop(scene, (2, 4, 25, 11))
        self.assertEqual(cropped['roi_origin'], (2, 4))
        self.assertEqual(cropped['sensor_crop'], (2, 3, 4, 5))
        for key in ('cube', 'left_cube', 'right_cube', 'left_cube_aligned'):
            np.testing.assert_array_equal(cropped[key], scene[key][:, 4:15, 2:27])
            self.assertFalse(np.shares_memory(cropped[key], scene[key]))
        for key in ('rgb_img', 'left_rgb_img', 'right_rgb_img', 'homography_mask'):
            np.testing.assert_array_equal(cropped[key], scene[key][4:15, 2:27])
            self.assertFalse(np.shares_memory(cropped[key], scene[key]))
        np.testing.assert_array_equal(cropped['base_bands']['R0'],
                                      scene['base_bands']['R0'][4:15, 2:27])
        cropped['base_bands']['R0'][:] = -1
        self.assertTrue((scene['base_bands']['R0'] >= 0).all())
        # Mapping in the algorithm frame must agree with full-image stereo mapping.
        point = np.array([7, 5, 1])
        full_point = point + [2, 4, 0]
        expected = scene['homography_matrix'] @ full_point
        expected = expected[:2] / expected[2] - [2, 4]
        mapped = cropped['homography_matrix'] @ point
        np.testing.assert_allclose(mapped[:2] / mapped[2], expected)

    def test_crop_handles_absent_eye_arrays(self):
        scene = full_scene()
        scene['left_cube'] = np.array([])
        scene['left_cube_aligned'] = None
        cropped = callbacks._apply_crop(scene, (2, 4, 25, 11))
        self.assertEqual(cropped['left_cube'].size, 0)
        self.assertIsNone(cropped['left_cube_aligned'])

    def test_full_and_legacy_segment_caches_select_the_same_pixels(self):
        scene = full_scene()
        segments = scene['base_bands']['R0']
        legacy = segments[4:15, 2:27]
        for crop in ((2, 4, 25, 11), (7, 6, 5, 3)):
            x, y, w, h = crop
            for cache in (segments, legacy):
                np.testing.assert_array_equal(
                    callbacks._crop_presegmented(cache, scene, crop),
                    segments[y:y+h, x:x+w],
                )
        with self.assertRaises(ValueError):
            callbacks._crop_presegmented(np.zeros((2, 3)), scene, (2, 4, 25, 11))

    def test_run_passes_trimmed_scene_and_cache_to_worker(self):
        scene = full_scene()
        model, view = SimpleNamespace(sparc_load_result=scene), Mock()
        algorithm, scenes = Mock(), Mock()
        with tempfile.TemporaryDirectory() as directory:
            scenes.get_scene_info.return_value = (directory, 'seq', 0, 'ZCAM')
            np.savez(Path(directory) / 'scene.npz',
                     segments=scene['base_bands']['R0'][4:15, 2:27])
            callbacks.run_algorithm(model, view, scenes, algorithm, 'scene',
                                    'sam.pth', {}, crop_rect=(7, 6, 5, 3))
        kwargs = algorithm.start_sparc.call_args.kwargs
        self.assertEqual(kwargs['load_result']['roi_origin'], (7, 6))
        self.assertEqual(kwargs['load_result']['rgb_img'].shape, (3, 5, 3))
        np.testing.assert_array_equal(kwargs['presegmented'],
                                      scene['base_bands']['R0'][6:9, 7:12])
        self.assertEqual(scene['rgb_img'].shape, (20, 30, 3))
        self.assertNotIn('roi_origin', scene)

    def test_completion_uses_run_origin_for_both_eyes_masks_and_spectra(self):
        scene = full_scene()
        result = SimpleNamespace(
            final_rois=[(1, 2, 3, 4)], instrument='ZCAM', wavelengths=[500],
            _load_result={'roi_origin': (7, 6)},
        )
        algorithm, spectra, colors, view = Mock(), Mock(), Mock(), Mock()
        algorithm.extract_roi_data.return_value = [{
            'roi': (1, 2, 3, 4), 'right_rect': (1, 2, 3, 4),
            'left_rect': (3, 1, 3, 4),
        }]
        spectra.update_roi_spectrum_dual.return_value = {'spectrum': [1.0]}
        colors.next.return_value = ((255, 0, 0), 'red')
        view.panel_image_editing.get_crop_rect.return_value = (100, 100, 2, 2)
        rois, _, _ = callbacks.on_sparc_complete(
            result, SimpleNamespace(sparc_load_result=scene), view,
            algorithm, spectra, colors,
        )
        self.assertEqual(rois[0]['right_rect'], (8, 8, 3, 4))
        self.assertEqual(rois[0]['left_rect'], (10, 7, 3, 4))
        expected_mask = np.zeros((20, 30), dtype=bool)
        expected_mask[8:12, 8:11] = True
        np.testing.assert_array_equal(rois[0]['mask'], expected_mask)
        spectra.update_roi_spectrum_dual.assert_called_once_with(
            scene, (10, 7, 3, 4), (8, 8, 3, 4), {'wavelengths': [500]},
        )
        view.panel_image_editing.get_crop_rect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
