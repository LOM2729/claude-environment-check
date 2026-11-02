"""Regression for empty Tk selections without opening windows or touching clients."""
from pathlib import Path
import queue
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lite.app import Window, label_index, selected_index


class Value:
    def __init__(self, value):self.value = value
    def get(self):return self.value


class Button:
    def configure(self, **kwargs):self.state = kwargs.get('state')


class LiteUIState(unittest.TestCase):
    def test_empty_or_changed_selection_is_not_an_integer_conversion(self):
        self.assertEqual(label_index('', []), -1)
        self.assertEqual(label_index('正在读取', ['1. Exit']), -1)
        self.assertEqual(label_index('2. Exit〔链式〕', ['1. Exit', '2. Exit〔链式〕']), 1)
        ui = Window.__new__(Window)
        ui.node_var = Value(''); ui.node_labels = []; ui.nodes = []; ui.busy = False
        ui.node_box = SimpleNamespace(current=lambda: -1)
        ui.service = SimpleNamespace(source=None, inspection=None)
        ui.export_button = Button()
        ui.update_actions()
        self.assertEqual(ui.export_button.state, 'disabled')
        self.assertEqual(selected_index(SimpleNamespace(current=lambda:1), Value('typed Tcl value'),
                                        ['1. Transit','2. Exit']),1)
        self.assertEqual(selected_index(SimpleNamespace(current=lambda:''), Value('unknown'),
                                        ['1. Transit']),-1)

    def test_callback_failure_does_not_stop_the_result_pump(self):
        ui = Window.__new__(Window); ui.closed=False; ui.busy=True
        class BrokenQueue:
            def get_nowait(self):raise ValueError('synthetic empty native value')
        ui.events=BrokenQueue();scheduled=[];errors=[]
        ui.root=SimpleNamespace(after=lambda delay, callback:scheduled.append((delay,callback)))
        ui.callback_error=lambda *args:errors.append(args)
        ui.drain()
        self.assertFalse(ui.busy)
        self.assertEqual(len(errors),1)
        self.assertEqual(scheduled[0][0],80)


if __name__ == '__main__':unittest.main()
