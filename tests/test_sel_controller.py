import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_sel_controller():
    """Load the exporter with lightweight stand-ins for its optional GUI/SPARC deps."""
    matplotlib = _module("matplotlib", use=lambda *_args, **_kwargs: None)
    matplotlib.__path__ = []
    pyplot = _module(
        "matplotlib.pyplot",
        subplots=MagicMock(),
        close=MagicMock(),
    )
    patches = _module("matplotlib.patches", Rectangle=MagicMock)

    rapidlooks = SimpleNamespace(CROP_SETTINGS={"crop": (0, 0, 0, 0)})
    asdf_settings = _module("asdf_settings", rapidlooks=rapidlooks)

    class QFileDialog:
        @staticmethod
        def getSaveFileName(*_args, **_kwargs):
            return "", ""

    pyqt = _module("PyQt5")
    pyqt.__path__ = []
    qt_widgets = _module("PyQt5.QtWidgets", QFileDialog=QFileDialog)

    sparc = _module("sparc")
    sparc.__path__ = []
    sparc_data = _module("sparc.data")
    sparc_data.__path__ = []
    loading = _module(
        "sparc.data.loading",
        create_rgb_stretch=MagicMock(),
        dcs_rgb=MagicMock(),
        observation_metadata=MagicMock(return_value={}),
    )
    sparc_visualization = _module("sparc.visualization")
    sparc_visualization.__path__ = []
    plotting = _module("sparc.visualization.plotting", plot_spectra_with_error=MagicMock())
    sparc_utils = _module("sparc.utils")
    sparc_utils.__path__ = []
    sel_writer = _module(
        "sparc.utils.sel_writer",
        export_sel=MagicMock(),
        read_sel=MagicMock(),
        filenames_from_load_result=MagicMock(),
    )

    stand_ins = {
        "matplotlib": matplotlib,
        "matplotlib.pyplot": pyplot,
        "matplotlib.patches": patches,
        "asdf_settings": asdf_settings,
        "PyQt5": pyqt,
        "PyQt5.QtWidgets": qt_widgets,
        "sparc": sparc,
        "sparc.data": sparc_data,
        "sparc.data.loading": loading,
        "sparc.visualization": sparc_visualization,
        "sparc.visualization.plotting": plotting,
        "sparc.utils": sparc_utils,
        "sparc.utils.sel_writer": sel_writer,
    }
    module_path = Path(__file__).parents[1] / "controllers" / "sel_controller.py"
    spec = importlib.util.spec_from_file_location("sel_controller_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module


sel_controller = _load_sel_controller()


class ExportContextTests(unittest.TestCase):
    @patch.object(sel_controller, "export_fits")
    @patch.object(sel_controller, "export_sel")
    @patch.object(sel_controller, "plot_spectra_with_error")
    @patch.object(sel_controller, "_save_annotated")
    @patch.object(sel_controller, "_render_bands")
    @patch.object(sel_controller.QFileDialog, "getSaveFileName")
    def test_exports_named_variants_for_both_rgb_images(
        self,
        get_save_filename,
        render_bands,
        save_annotated,
        plot_spectra,
        _export_sel,
        _export_fits,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "context"
            get_save_filename.return_value = (str(output_dir), "")
            render_bands.return_value = np.zeros((8, 8, 3), dtype=np.uint8)
            plot_spectra.return_value = MagicMock()

            load_result = {
                "id": "scene",
                "instrument": "ZCAM",
                "base_bands": {},
            }
            model = SimpleNamespace(sparc_load_result=load_result)
            view = MagicMock()
            rois = [{
                "right_rect": (1, 2, 3, 4),
                "left_rect": (4, 3, 2, 1),
                "spectrum": [0.1],
                "std": [0.01],
                "wavelengths": [500],
            }]

            sel_controller.export_context(
                view,
                model,
                rois,
                [(255, 0, 0)],
                ["red"],
                MagicMock(),
            )

            named_calls = [
                item for item in save_annotated.call_args_list
                if item.kwargs.get("roi_names") is not None
            ]
            self.assertEqual(
                [item.args[3].name for item in named_calls],
                [
                    "scene_right_rgb_with_roi_names.png",
                    "scene_left_rgb_with_roi_names.png",
                ],
            )
            self.assertEqual(
                [item.kwargs["roi_names"] for item in named_calls],
                [["red"], ["red"]],
            )
            self.assertEqual(save_annotated.call_count, 6)
            view.show_status_message.assert_called_once_with(
                f"Context exported to {output_dir}"
            )


class SingleEyeSelTests(unittest.TestCase):
    @patch.object(sel_controller, "filenames_from_load_result", return_value=([], []))
    @patch.object(sel_controller, "_write_sel")
    def test_export_keeps_empty_placeholder_for_missing_eye(
        self, write_sel, _filenames
    ):
        load_result = {
            "id": "scene",
            "instrument": "ZCAM",
            "base_bands": {"R0": np.zeros((8, 9), dtype=float)},
        }
        model = SimpleNamespace(sparc_load_result=load_result)
        color_manager = MagicMock()
        color_manager.merspect_index.side_effect = [4, 5, 6]
        rois = [
            {"left_rect": (1, 2, 3, 4), "right_rect": (5, 6, 7, 8)},
            {"left_rect": (9, 10, 11, 12), "right_rect": None},
            {"left_rect": None, "right_rect": (13, 14, 15, 16)},
        ]

        sel_controller.export_sel(
            MagicMock(), model, rois, ["red", "green", "blue"],
            color_manager, output_path="single-eye.sel",
        )

        kwargs = write_sel.call_args.kwargs
        np.testing.assert_array_equal(
            kwargs["final_left_rois"],
            np.array([(1, 2, 3, 4), (9, 10, 11, 12), (0, 0, 0, 0)]),
        )
        np.testing.assert_array_equal(
            kwargs["final_rois"],
            np.array([(5, 6, 7, 8), (0, 0, 0, 0), (13, 14, 15, 16)]),
        )
        self.assertEqual(kwargs["label_ids"], [4, 5, 6])

    def test_reader_aligns_mixed_eye_rectangles_by_label(self):
        right = np.array([(1, 1, 3, 3), (6, 6, 4, 4)], dtype=np.int32)
        left = np.array([(2, 2, 3, 3), (5, 5, 2, 2)], dtype=np.int32)
        blocks = [SimpleNamespace(decompressed=b"") for _ in range(4)]
        module = sel_controller._sel_writer_module

        def rois_from_block(payload, _background):
            return ((right, [4, 6]) if payload == b"right"
                    else (left, [4, 5]))

        blocks[2].decompressed = b"left"
        blocks[3].decompressed = b"right"
        attrs = {
            "_read_template": MagicMock(return_value=blocks),
            "_rois_from_block": MagicMock(side_effect=rois_from_block),
            "_normalize_instrument": MagicMock(return_value="mcz"),
            "_MASK_DEFAULTS": {"mcz": {"background": 0}},
            "_LSEL_IDX": 2,
            "_RSEL_IDX": 3,
        }
        originals = {name: getattr(module, name, None) for name in attrs}
        missing = {name for name in attrs if not hasattr(module, name)}
        try:
            for name, value in attrs.items():
                setattr(module, name, value)
            aligned_right, aligned_left, labels = sel_controller._read_sel_aligned(
                "mixed.sel", "ZCAM"
            )
        finally:
            for name, value in originals.items():
                if name in missing:
                    delattr(module, name)
                else:
                    setattr(module, name, value)

        self.assertEqual(labels, [4, 5, 6])
        np.testing.assert_array_equal(
            aligned_right,
            np.array([(1, 1, 3, 3), (0, 0, 0, 0), (6, 6, 4, 4)]),
        )
        np.testing.assert_array_equal(
            aligned_left,
            np.array([(2, 2, 3, 3), (5, 5, 2, 2), (0, 0, 0, 0)]),
        )

    def test_reader_restores_disconnected_regions_in_one_color_class(self):
        right_mask = np.zeros((8, 10), dtype=np.uint8)
        # SEL rows are bottom-origin, so these become image y=5 and y=1.
        right_mask[1:3, 2:5] = 4
        right_mask[5:7, 7:9] = 4
        left_mask = np.zeros_like(right_mask)
        blocks = [SimpleNamespace(decompressed=b'') for _ in range(4)]
        blocks[2].decompressed = left_mask.tobytes()
        blocks[3].decompressed = right_mask.tobytes()
        module = sel_controller._sel_writer_module
        attrs = {
            '_read_template': MagicMock(return_value=blocks),
            '_parse_mask_header': MagicMock(return_value=(10, 8, 0)),
            '_normalize_instrument': MagicMock(return_value='mcz'),
            '_MASK_DEFAULTS': {'mcz': {'background': 0}},
            '_LSEL_IDX': 2,
            '_RSEL_IDX': 3,
        }
        originals = {name: getattr(module, name, None) for name in attrs}
        missing = {name for name in attrs if not hasattr(module, name)}
        try:
            for name, value in attrs.items():
                setattr(module, name, value)
            right, left, labels = sel_controller._read_sel_regions(
                'same-color.sel', 'ZCAM'
            )
        finally:
            for name, value in originals.items():
                if name in missing:
                    delattr(module, name)
                else:
                    setattr(module, name, value)

        self.assertEqual(labels, [4, 4])
        np.testing.assert_array_equal(
            right,
            np.array([(2, 5, 3, 2), (7, 1, 2, 2)], dtype=np.int32),
        )
        np.testing.assert_array_equal(
            left,
            np.zeros((2, 4), dtype=np.int32),
        )


class SingleEyeFitsTests(unittest.TestCase):
    def test_export_writes_only_present_eye_hdus(self):
        written = {}

        class Header(dict):
            pass

        class Hdu:
            def __init__(self, data=None, header=None):
                self.data = data
                self.header = header

        class HduList(list):
            def writeto(self, path, overwrite=False):
                written["path"] = path
                written["overwrite"] = overwrite
                written["hdus"] = list(self)

        fits_module = _module(
            "astropy.io.fits",
            Header=Header,
            PrimaryHDU=Hdu,
            ImageHDU=Hdu,
            HDUList=HduList,
        )
        astropy = _module("astropy")
        astropy.__path__ = []
        astropy_io = _module("astropy.io", fits=fits_module)
        astropy_io.__path__ = []
        model = SimpleNamespace(sparc_load_result={
            "id": "scene",
            "rgb_img": np.zeros((20, 30, 3), dtype=np.uint8),
        })
        rois = [
            {"left_rect": (1, 2, 3, 4), "right_rect": None,
             "metadata": {"FEATURE": "rock", "MEMBER": "obsolete"}},
            {"left_rect": None, "right_rect": (5, 6, 7, 8)},
            {"left_rect": (10, 10, 2, 2), "right_rect": None},
        ]

        with patch.dict(sys.modules, {
            "astropy": astropy,
            "astropy.io": astropy_io,
            "astropy.io.fits": fits_module,
        }):
            sel_controller.export_fits(
                MagicMock(), model, rois, ["red", "green", "red"],
                output_path="single-eye.fits",
            )

        self.assertEqual([h.header["EYE"] for h in written["hdus"]],
                         ["left", "right"])
        self.assertEqual([h.header["NAME"] for h in written["hdus"]],
                         ["red", "green"])
        for hdu in written["hdus"]:
            self.assertEqual(set(hdu.header), {
                "NAME", "EYE", "SOURCEFN", "EXTNAME", "IMAGEREF",
            })
            self.assertEqual(hdu.header["SOURCEFN"], "ROIStudio")
            self.assertEqual(hdu.header["IMAGEREF"], "scene")
        # Both red rectangles are one selection class and share one union mask.
        self.assertEqual(int(written["hdus"][0].data.sum()), 16)
        self.assertEqual(int(written["hdus"][1].data.sum()), 56)

    def test_component_rects_keep_disconnected_class_regions_editable(self):
        mask = np.zeros((8, 10), dtype=np.uint8)
        mask[1:3, 2:5] = 1
        mask[5:7, 7:9] = 1

        self.assertEqual(
            sel_controller._mask_rects(mask),
            [(2, 1, 3, 2), (7, 5, 2, 2)],
        )

    def test_pancam_keeps_existing_rich_fits_metadata(self):
        written = {}

        class Header(dict):
            pass

        class Hdu:
            def __init__(self, data=None, header=None):
                self.data = data
                self.header = header

        class HduList(list):
            def writeto(self, _path, overwrite=False):
                written["overwrite"] = overwrite
                written["hdus"] = list(self)

        fits_module = _module(
            "astropy.io.fits",
            Header=Header,
            PrimaryHDU=Hdu,
            ImageHDU=Hdu,
            HDUList=HduList,
        )
        astropy = _module("astropy")
        astropy.__path__ = []
        astropy_io = _module("astropy.io", fits=fits_module)
        astropy_io.__path__ = []
        model = SimpleNamespace(sparc_load_result={
            "id": "Sol1156_p2580v17_PMA92_madeline_english",
            "instrument": "PCAM",
            "rgb_img": np.zeros((20, 30, 3), dtype=np.uint8),
        })
        rois = [{
            "left_rect": (1, 2, 3, 4),
            "right_rect": None,
            "metadata": {"FEATURE": "rock"},
        }]

        with patch.dict(sys.modules, {
            "astropy": astropy,
            "astropy.io": astropy_io,
            "astropy.io.fits": fits_module,
        }), patch.object(
            sel_controller, "observation_metadata",
            return_value={"INSTRUMENT": "PCAM", "SOL": 1156},
        ):
            sel_controller.export_fits(
                MagicMock(), model, rois, ["red"],
                output_path="pancam.fits",
            )

        header = written["hdus"][0].header
        self.assertEqual(header["ROIINDEX"], 0)
        self.assertEqual(header["FEATURE"], "rock")
        self.assertEqual(header["INSTRUMENT"], "PCAM")
        self.assertEqual(header["SOL"], 1156)

    def test_import_preserves_absent_eye(self):
        mask = np.zeros((20, 30), dtype=np.uint8)
        mask[2:6, 3:8] = 1
        hdu = SimpleNamespace(
            data=mask,
            header={"NAME": "red", "EYE": "left"},
        )

        class Opened(list):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        fits_module = _module(
            "astropy.io.fits",
            open=lambda _path: Opened([hdu]),
        )
        astropy = _module("astropy")
        astropy.__path__ = []
        astropy_io = _module("astropy.io", fits=fits_module)
        astropy_io.__path__ = []
        roi_metadata = _module(
            "views.panels.roi_metadata",
            metadata_fields=lambda _instrument: (),
        )
        model = SimpleNamespace(sparc_load_result={
            "id": "scene",
            "instrument": "ZCAM",
            "rgb_img": np.zeros((20, 30, 3), dtype=np.uint8),
        })
        spectra = MagicMock()
        spectra.update_roi_spectrum_dual.return_value = {"spectrum": [1.0]}
        colors = MagicMock()
        colors.resolve_name.return_value = "red"
        colors.color.return_value = (255, 0, 0)

        with patch.dict(sys.modules, {
            "astropy": astropy,
            "astropy.io": astropy_io,
            "astropy.io.fits": fits_module,
            "views.panels.roi_metadata": roi_metadata,
        }):
            outcome = sel_controller.load_fits(
                MagicMock(), model, {}, spectra, True, colors,
                fits_path="left-only.fits",
            )

        roi = outcome[0][0]
        self.assertEqual(roi["left_rect"], (3, 2, 5, 4))
        self.assertIsNone(roi["right_rect"])
        self.assertIsNone(roi["roi"])


class SaveAnnotatedTests(unittest.TestCase):
    @patch.object(sel_controller.plt, "close")
    @patch.object(sel_controller.plt, "subplots")
    def test_draws_each_roi_name_with_gui_style_and_box_aligned_to_roi(
        self, subplots, _close
    ):
        fig = MagicMock()
        ax = MagicMock()
        subplots.return_value = (fig, ax)
        colors = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]

        sel_controller._save_annotated(
            np.zeros((8, 8, 3), dtype=np.uint8),
            [(1, 2, 3, 4), (6, 6, 2, 2)],
            colors,
            Path("annotated.png"),
            roi_names=["red", "green"],
        )

        self.assertEqual(ax.annotate.call_count, 2)
        self.assertEqual(
            [(item.args[0], item.kwargs["color"]) for item in ax.annotate.call_args_list],
            [("red", colors[0]), ("green", colors[1])],
        )
        expected_padding = (
            sel_controller._ROI_LABEL_FONT_SIZE * sel_controller._ROI_LABEL_PADDING
        )
        for rect, text_call in zip(
            [(1, 2, 3, 4), (6, 6, 2, 2)], ax.annotate.call_args_list
        ):
            self.assertEqual(text_call.kwargs["xy"], rect[:2])
            self.assertEqual(
                text_call.kwargs["xytext"],
                (expected_padding, expected_padding),
            )
            self.assertEqual(text_call.kwargs["textcoords"], "offset points")
            self.assertEqual(text_call.kwargs["fontfamily"], "Arial")
            self.assertEqual(
                text_call.kwargs["fontsize"], sel_controller._ROI_LABEL_FONT_SIZE
            )
            self.assertEqual(text_call.kwargs["fontweight"], "normal")
            self.assertEqual(text_call.kwargs["horizontalalignment"], "left")
            self.assertEqual(text_call.kwargs["verticalalignment"], "bottom")
            self.assertFalse(text_call.kwargs["clip_on"])
            self.assertFalse(text_call.kwargs["annotation_clip"])
            self.assertEqual(
                text_call.kwargs["bbox"]["boxstyle"],
                f"square,pad={sel_controller._ROI_LABEL_PADDING}",
            )
            self.assertEqual(
                text_call.kwargs["bbox"]["facecolor"],
                (20 / 255, 20 / 255, 20 / 255),
            )
            self.assertEqual(text_call.kwargs["bbox"]["alpha"], 200 / 255)


if __name__ == "__main__":
    unittest.main()
