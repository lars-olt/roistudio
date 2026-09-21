import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

# The exporter already loads with GUI/SPARC stand-ins there
from test_sel_controller import sel_controller


def _load_slides():
    """Load the renderer by path"""
    module_path = Path(__file__).parents[1] / "utils" / "slides.py"
    spec = importlib.util.spec_from_file_location("slides_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


slides = _load_slides()

_COLUMNS = [('FEATURE', 'Feature'), ('FEATURE_SUBTYPE', 'Feature subtype'),
            ('DISTANCE', 'Distance')]
_SUBS    = [('FLOAT', 'Float'), ('DESCRIPTION', 'Description')]


def _rois(count):
    return [{
        'name': f"roi{i}",
        'color': (0.2, 0.4, 0.6),
        'FEATURE': 'rock',
        'FEATURE_SUBTYPE': 'thick dust',
        'DISTANCE': 'midfield',
        'FLOAT': 'in-place',
        'DESCRIPTION': 'a rock',
    } for i in range(count)]


# A slide is written even when panels are missing, and spills onto a second
# page rather than dropping ROIs it cannot fit.
class SlideRenderingTests(unittest.TestCase):
    def test_writes_a_pdf_with_missing_panels_as_placeholders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dest = Path(temp_dir) / "scene_summary.pdf"
            panels = [(str(Path(temp_dir) / "absent.png"), "Left eye RGB"),
                        (None, "Right eye DCS"),
                        (None, "Spectra")]

            slides.build_slide(str(dest), "scene", "sol 1941   |   3 ROIs",
                                panels, _rois(3), _COLUMNS, _SUBS)

            self.assertTrue(dest.is_file())
            self.assertGreater(dest.stat().st_size, 0)

    def test_non_pdf_destination_writes_page_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dest = Path(temp_dir) / "scene_summary.png"

            slides.build_slide(str(dest), "scene", "", [], _rois(1),
                                _COLUMNS, _SUBS)

            self.assertTrue(dest.is_file())

    def test_table_stops_at_a_full_cell_and_the_rest_spill_to_page_two(self):
        rois = _rois(20)
        page = slides._Page()
        fig = page.figure()
        x, y, cell_h = page.cell(3)

        drawn = slides._draw_roi_table(
            page, fig, x, y + slides._CAPTION_PX, rois, _COLUMNS, _SUBS,
            slides._CELL_PX, cell_h,
        )

        self.assertEqual(drawn, slides._ROWS_PER_CELL)
        with tempfile.TemporaryDirectory() as temp_dir:
            dest = Path(temp_dir) / "scene_summary.pdf"
            slides.build_slide(str(dest), "scene", "", [], rois,
                                _COLUMNS, _SUBS)
            self.assertIn(b"/Count 2", dest.read_bytes())

    def test_a_dropped_write_leaves_no_partial_slide(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dest = Path(temp_dir) / "scene_summary.png"
            figure = slides._Page().figure()
            figure.savefig = MagicMock(side_effect=OSError("network went away"))

            with self.assertRaises(OSError):
                slides._write_slide([figure], str(dest))

            self.assertEqual(list(Path(temp_dir).iterdir()), [])


# Fields differ between the instruments.
class SlideFieldTests(unittest.TestCase):
    def test_zcam_columns_and_sub_line(self):
        columns, subs = sel_controller._slide_fields('ZCAM')

        self.assertEqual([key for key, _label in columns],
                        ['FEATURE', 'FEATURE_SUBTYPE', 'DISTANCE'])
        self.assertEqual([key for key, _label in subs],
                        ['FLOAT', 'FORMATION', 'GRAIN_SIZE', 'MEMBER', 'DESCRIPTION'])

    def test_pancam_columns_and_sub_line(self):
        columns, subs = sel_controller._slide_fields('PCAM')

        self.assertEqual([key for key, _label in columns],
                        ['FEATURE', 'FEATURE_SUBTYPE', 'DISTANCE'])
        self.assertEqual([key for key, _label in subs],
                        ['FLOAT', 'TEXTURE', 'DESCRIPTION'])


class SlidePanelTests(unittest.TestCase):
    def test_zcam_puts_rgb_on_the_left_and_names_on_it(self):
        panels = sel_controller._slide_panels(Path("out"), "scene", "ZCAM")

        self.assertEqual([Path(path).name for path, _caption in panels], [
            "scene_left_rgb_with_roi_names.png",
            "scene_right_dcs.png",
            "scene_spectra.png",
        ])
        self.assertEqual([caption for _path, caption in panels],
                        ["Left eye RGB", "Right eye DCS", "Spectra"])

    def test_pancam_puts_rgb_on_the_right_and_names_on_it(self):
        panels = sel_controller._slide_panels(Path("out"), "scene", "PCAM")

        self.assertEqual([Path(path).name for path, _caption in panels], [
            "scene_left_dcs.png",
            "scene_right_rgb_with_roi_names.png",
            "scene_spectra.png",
        ])
        self.assertEqual([caption for _path, caption in panels],
                        ["Left eye DCS", "Right eye RGB", "Spectra"])


class SlideSubtitleTests(unittest.TestCase):
    def test_zcam_reads_sol_and_sequence_off_a_product_filename(self):
        stem = "ZL0_1941_0839254206_864IOF_N0902288ZCAM04437_0630LMA02"
        with patch.object(sel_controller, "filenames_from_load_result",
                            return_value=([stem], [stem])):
            subtitle = sel_controller._slide_subtitle({}, 'ZCAM', 14)

        self.assertEqual(subtitle, "sol 1941   |   ZCAM04437   |   14 ROIs")

    def test_zcam_falls_back_to_the_roi_count_alone(self):
        with patch.object(sel_controller, "filenames_from_load_result",
                            return_value=(["scene"], ["scene"])):
            subtitle = sel_controller._slide_subtitle({}, 'ZCAM', 1)

        self.assertEqual(subtitle, "1 ROI")

    def test_pancam_uses_the_observation_metadata(self):
        meta = {'ROVER': 'MERA', 'SOL': 21, 'SEQ_ID': 'p2530', 'PMA': 1}
        with patch.object(sel_controller, "observation_metadata",
                            return_value=meta):
            subtitle = sel_controller._slide_subtitle({}, 'PCAM', 4)

        self.assertEqual(subtitle,
                        "MERA   |   sol 0021   |   p2530   |   PMA 1   |   4 ROIs")


class SlideRowTests(unittest.TestCase):
    def test_rows_are_selection_classes_with_0_1_colors(self):
        rois = [
            {'left_rect': (1, 2, 3, 4), 'metadata': {'FEATURE': 'rock'}},
            {'left_rect': (5, 6, 7, 8), 'metadata': {'FEATURE': 'rock'}},
            {'left_rect': (9, 9, 1, 1), 'metadata': {'FEATURE': 'soil'}},
        ]
        with patch("utils.slides.build_slide") as build_slide, \
            patch.object(sel_controller, "filenames_from_load_result",
                            return_value=([], [])):
            sel_controller._export_slide(
                {'instrument': 'ZCAM'}, Path("out"), "scene", rois,
                [(255, 0, 0), (255, 0, 0), (0, 255, 0)],
                ['red', 'red', 'green'],
            )

        rows = build_slide.call_args.args[4]
        self.assertEqual([row['name'] for row in rows], ['red', 'green'])
        self.assertEqual([row['color'] for row in rows],
                        [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
        self.assertEqual([row['FEATURE'] for row in rows], ['rock', 'soil'])


# The slide is written after its panels, and a slide that fails does not turn a
# finished export into a reported failure.
class ContextSlideTests(unittest.TestCase):
    def _export(self, output_dir, export_slide):
        load_result = {"id": "scene", "instrument": "ZCAM", "base_bands": {}}
        rois = [{
            "right_rect": (1, 2, 3, 4),
            "left_rect": (4, 3, 2, 1),
            "spectrum": [0.1],
            "std": [0.01],
            "wavelengths": [500],
        }]
        view = MagicMock()

        with patch.object(sel_controller.QFileDialog, "getSaveFileName",
                        return_value=(str(output_dir), "")), \
            patch.object(sel_controller, "export_sel"), \
            patch.object(sel_controller, "export_fits"), \
            patch.object(sel_controller, "plot_spectra_with_error",
                        return_value=MagicMock()), \
            patch.object(sel_controller, "_render_bands",
                        return_value=np.zeros((8, 8, 3), dtype=np.uint8)), \
            patch.object(sel_controller, "_save_annotated") as save_annotated, \
            patch.object(sel_controller, "_export_slide", export_slide):
            order = MagicMock()
            order.attach_mock(save_annotated, "panel")
            order.attach_mock(export_slide, "slide")
            sel_controller.export_context(
                view, SimpleNamespace(sparc_load_result=load_result), rois,
                [(255, 0, 0)], ["red"], MagicMock(),
            )
        return view, order

    def test_slide_is_written_after_the_panels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "context"
            view, order = self._export(output_dir, MagicMock())

            names = [name for name, _args, _kwargs in order.mock_calls]
            self.assertEqual(names[-1], "slide")
            self.assertIn("panel", names)
            view.show_status_message.assert_called_once_with(
                f"Context exported to {output_dir}"
            )

    def test_a_failed_slide_leaves_the_export_standing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "context"
            failing = MagicMock(side_effect=RuntimeError("no room on disk"))
            view, _order = self._export(output_dir, failing)

            messages = [call.args[0] for call in
                        view.show_status_message.call_args_list]
            self.assertEqual(messages, [
                f"Context exported to {output_dir}",
                "Context exported, but the summary slide failed: no room on disk",
            ])


if __name__ == '__main__':
    unittest.main()
