import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch


ROOT = Path(__file__).parents[1]


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_algorithm_controller():
    path = ROOT / 'controllers' / 'algorithm_controller.py'
    spec = importlib.util.spec_from_file_location(
        'algorithm_controller_under_test', path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AlgorithmController


def _load_image_editing_panel():
    views = _module('views')
    views.__path__ = []
    panels = _module('views.panels')
    panels.__path__ = []
    stand_ins = {
        'views': views,
        'views.panels': panels,
        'views.canvas': _module(
            'views.canvas', DualCanvasContainer=Mock,
        ),
        'views.widgets': _module(
            'views.widgets',
            ToolbarButton=Mock,
            LoadingIndicator=Mock,
            ColorSwatchGrid=Mock,
            toolbar_button_size=lambda: (24, 24),
        ),
        'views.panels.stretch_bar': _module(
            'views.panels.stretch_bar', StretchBar=Mock,
        ),
    }
    path = ROOT / 'views' / 'panels' / 'image_editing.py'
    spec = importlib.util.spec_from_file_location(
        'views.panels.image_editing_under_test', path
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module.ImageEditingPanel


def _load_sparc_runner(run_from_load_result):
    class Config:
        def __init__(self, **values):
            self.__dict__.update(values)

    release_cuda_memory = Mock()
    sparc = _module('sparc')
    sparc.__path__ = []
    core = _module('sparc.core')
    core.__path__ = []
    utils = _module('sparc.utils')
    utils.__path__ = []
    stand_ins = {
        'sparc': sparc,
        'sparc.core': core,
        'sparc.core.functional': _module(
            'sparc.core.functional',
            run_sparc=Mock(),
            run_sparc_from_load_result=run_from_load_result,
        ),
        'sparc.core.config': _module(
            'sparc.core.config',
            SparcConfig=Config,
            LoadConfig=Config,
            SegmentConfig=Config,
            ROIConfig=Config,
            SpectralConfig=Config,
            SegmentationBackend=types.SimpleNamespace(GPU='gpu'),
            ROIBackend=types.SimpleNamespace(THREADED='threaded'),
        ),
        'sparc.utils': utils,
        'sparc.utils.memory': _module(
            'sparc.utils.memory', release_cuda_memory=release_cuda_memory,
        ),
    }
    path = ROOT / 'workers' / 'sparc_runner.py'
    spec = importlib.util.spec_from_file_location(
        'sparc_runner_under_test', path
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module.SparcRunThread, release_cuda_memory


AlgorithmController = _load_algorithm_controller()
ImageEditingPanel = _load_image_editing_panel()


class FakeSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self._callbacks):
            callback(*args)


class FakeThread:
    def __init__(self):
        self.status_update = FakeSignal()
        self.sparc_complete = FakeSignal()
        self.sparc_error = FakeSignal()
        self.finished = FakeSignal()
        self.running = False
        self.deleted = False

    def start(self):
        self.running = True

    def isRunning(self):
        return self.running

    def finish(self):
        self.running = False
        self.finished.emit()

    def deleteLater(self):
        self.deleted = True


# Only one SPARC run should exist, and every run should release its large data.
class AlgorithmWorkerLifecycleTests(unittest.TestCase):
    def test_duplicate_run_is_rejected_and_finished_thread_is_disposed(self):
        controller = AlgorithmController()
        thread = FakeThread()
        statuses = []
        stopped = []
        controller.status_update.connect(statuses.append)
        controller.stopped.connect(lambda: stopped.append(True))

        with patch.object(controller, '_new_thread', return_value=thread) as create:
            first = controller.start_sparc('', '', None, 0, 'ZCAM')
            second = controller.start_sparc('', '', None, 0, 'ZCAM')

        self.assertTrue(first)
        self.assertFalse(second)
        create.assert_called_once()
        self.assertEqual(statuses, ['SPARC is already running.'])

        thread.finish()

        self.assertIsNone(controller._sparc_thread)
        self.assertTrue(thread.deleted)
        self.assertEqual(stopped, [True])

    def test_failed_worker_releases_scene_references_and_cuda_cache(self):
        run_pipeline = Mock(side_effect=RuntimeError('pipeline failed'))
        thread_type, release_cuda_memory = _load_sparc_runner(run_pipeline)
        thread = thread_type(
            '', '', None, 0, 'ZCAM',
            load_result={'cube': 'large scene'},
            presegmented=object(),
        )
        errors = []
        thread.sparc_error.connect(errors.append)

        thread.run()

        self.assertIsNone(thread.load_result)
        self.assertIsNone(thread.presegmented)
        self.assertEqual(release_cuda_memory.call_args_list, [call()])
        self.assertEqual(len(errors), 1)
        self.assertIn('RuntimeError: pipeline failed', errors[0])

    def test_successful_worker_returns_result_then_releases_scene_memory(self):
        result = object()
        run_pipeline = Mock(return_value=result)
        thread_type, release_cuda_memory = _load_sparc_runner(run_pipeline)
        thread = thread_type(
            '', '', None, 0, 'ZCAM',
            load_result={'cube': 'large scene'},
            presegmented=object(),
        )
        completed = []
        errors = []
        thread.sparc_complete.connect(completed.append)
        thread.sparc_error.connect(errors.append)

        thread.run()

        self.assertEqual(completed, [result])
        self.assertEqual(errors, [])
        self.assertIsNone(thread.load_result)
        self.assertIsNone(thread.presegmented)
        release_cuda_memory.assert_called_once_with()


# Loading should lock the Full run button and remain safe when Lite has no button.
class RunButtonLifecycleTests(unittest.TestCase):
    def test_loading_state_disables_and_restores_run_button(self):
        panel = Mock(run_button=Mock(), loading_indicator=Mock())

        ImageEditingPanel.start_loading(panel)
        panel.run_button.setEnabled.assert_called_once_with(False)
        panel.loading_indicator.start_loading.assert_called_once_with()

        ImageEditingPanel.stop_loading(panel)
        panel.loading_indicator.stop_loading.assert_called_once_with()
        panel.run_button.setEnabled.assert_called_with(True)

    def test_lite_loading_state_does_not_require_an_algorithm_button(self):
        panel = Mock(run_button=None, loading_indicator=Mock())

        ImageEditingPanel.start_loading(panel)
        ImageEditingPanel.stop_loading(panel)

        panel.loading_indicator.start_loading.assert_called_once_with()
        panel.loading_indicator.stop_loading.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
