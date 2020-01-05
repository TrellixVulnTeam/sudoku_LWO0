from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.properties import StringProperty, ObjectProperty, ListProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from classes import Board
from database import Database
from __init__ import *
import re
import threading

DARK_HIGHLIGHT = (0.1568627450980392, 0.16862745098039217, 0.18823529411764706, 1)  # Darkest Gray
BACKGROUND_COLOR = (0.18823529411764706, 0.19215686274509805, 0.21176470588235294, 1)  # Dark gray
ELEMENT_COLOR = (0.21176470588235294, 0.2235294117647059, 0.25882352941176473, 1)  # Medium Gray
LIGHT_HIGHLIGHT = (0.39215686274509803, 0.396078431372549, 0.41568627450980394, 1)  # Lighter Gray
TEXT_COLOR = (0.6705882352941176, 0.6705882352941176, 0.6705882352941176, 1)  # Lightest Gray
APP_COLORS = [DARK_HIGHLIGHT, BACKGROUND_COLOR, ELEMENT_COLOR, LIGHT_HIGHLIGHT, TEXT_COLOR]

ITEM_ROW_HEIGHT = 72
TEXT_BASE_SIZE = 40

Window.size = (round(1440 * 1.618) / 2, 1440 / 2)


# Window.borderless = True


class TaskButton(ButtonBehavior, Image):
    """Callback based buttons for logical execution"""

    buttons = {
        'Hint': None,
        'Show Hotkeys': None,
        'Open Puzzle': None,
        'Solve': None,
        'Reset': None,
        'Settings': None,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._register_callbacks)  # ensure app is running before trying to resolve references

    def _register_callbacks(self, _):
        """Assign callbacks to buttons *after* app has been built"""
        app = App.get_running_app()
        self.buttons['Solve'] = app.root.start_second_thread
        self.buttons['Reset'] = app.reset
        self.buttons['Open Puzzle'] = app.root.puzzle_picker
        self.buttons['Random'] = PuzzlePicker.random
        self.buttons['Easy'] = PuzzlePicker.easy
        self.buttons['Intermediate'] = PuzzlePicker.med
        self.buttons['Expert'] = PuzzlePicker.hard

    def task_button_callback(self, button_text):
        try:
            callback = self.buttons[button_text]
            callback.__call__()
        except AttributeError:
            print(f'No callback present for <{button_text}>.')
        except KeyError:
            print(f'No key present for <{button_text}>.')


class TaskButtonLayout(FloatLayout):
    """Layout for single buttons and names"""

    button_text = StringProperty()
    image_path = StringProperty()


class ToggleLayout(FloatLayout):
    """Layout that holds pairs of toggle buttons"""

    pair_name = StringProperty()
    toggle_on_cb = ObjectProperty()
    toggle_off_cb = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.guides_on = NineBy.instance.guides_on
        self.guides_off = NineBy.instance.guides_off

    @staticmethod
    def inspections_on():
        app = App.get_running_app()
        setattr(app, 'inspections', True)
        conflicts = set()
        for tile in app.board.tiles.values():
            _conflicts = app.board.validate(tile)
            conflicts = conflicts | _conflicts

        if None in conflicts:
            conflicts.remove(None)

        for pos in conflicts:
            tile = Tile.tiles[pos]
            tile.label.color = (.6, .1, .1, 1)
        Tile.conflicts = conflicts

    @staticmethod
    def inspections_off():
        app = App.get_running_app()
        setattr(app, 'inspections', False)
        if Tile.conflicts:
            for pos in Tile.conflicts:
                tile = Tile.tiles[pos]
                tile.label.color = app.text_color
        Tile.conflicts = None


class PanelToggle(ToggleButton):
    """Toggles for PanelLayout"""

    def on_touch_down(self, touch):
        if self.state == 'down':
            pass
        else:
            super().on_touch_down(touch)


class Panel(FloatLayout):
    """Holds buttons on sidebar"""


class TileBackground(Label):
    """Background for entry and value label"""


class Tile(RelativeLayout):
    """Tile holding various widgets for sudoku tile functionality"""

    tiles = {}
    conflicts = None

    def __init__(self, position, **kwargs):
        self.locked = False
        self.grid_position = position
        super().__init__(**kwargs)

        self.focus_next = self.focus_previous = None
        self.directional_focus = {}
        Tile.tiles[self.grid_position] = self

        self.background = TileBackground()
        self.add_widget(self.background)

        self.input = TileInput(size_hint=(.95, .95),
                               pos_hint={'y': -0.125}
                               )
        self.input.bind(focus=lambda x, y: self.input.on_focus)
        self.add_widget(self.input)

        self.label = TileLabel(size_hint=(.95, .95),
                               # pos_hint={'x': 0.025, 'y': 0},
                               )
        self.add_widget(self.label)

        self.guesses = TileGuesses(size_hint=(.95, .95),
                                   # pos_hint={'x': 0.025, 'y': 0.025},
                                   )
        self.add_widget(self.guesses)

    def get_focus_next(self):
        return self.focus_next

    def get_focus_previous(self):
        return self.focus_previous

    def set_focus_behavior(self):

        def calculate_next_focus(x, y):
            dx_next = x + 1
            dy_next = y

            if dx_next == 9:
                dx_next = 0
                dy_next = y - 1

            if dy_next == -1:
                dy_next = 8

            return dx_next, dy_next

        def calculate_prev_focus(x, y):
            dx_prev = x - 1
            dy_prev = y

            if dx_prev == -1:
                dx_prev = 8
                dy_prev = y + 1

            if dy_prev == 9:
                dy_prev = 0

            return dx_prev, dy_prev

        def calculate_directional_focus(x, y, delta: (int, int)):
            dx = x + delta[0]
            dy = y + delta[1]

            if dx == -1:
                dx = 8
            elif dx == 9:
                dx = 0
            if dy == -1:
                dy = 8
            elif dy == 9:
                dy = 0

            return dx, dy

        next_x, next_y = calculate_next_focus(*self.grid_position)
        _next = Tile.tiles[(next_x, next_y)]

        while _next.locked:
            next_x, next_y = calculate_next_focus(next_x, next_y)
            _next = Tile.tiles[(next_x, next_y)]

        self.focus_next = _next

        prev_x, prev_y = calculate_prev_focus(*self.grid_position)
        _prev = Tile.tiles[(prev_x, prev_y)]

        while _prev.locked:
            prev_x, prev_y = calculate_prev_focus(prev_x, prev_y)
            _prev = Tile.tiles[(prev_x, prev_y)]

        self.focus_previous = _prev

        for direction in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            _x, _y = self.grid_position
            next_x, next_y = calculate_directional_focus(_x, _y, direction)
            _next = Tile.tiles[(next_x, next_y)]
            while _next.locked:
                next_x, next_y = calculate_directional_focus(next_x, next_y, direction)
                _next = Tile.tiles[(next_x, next_y)]

            self.directional_focus[direction] = _next




class TileGuesses(GridLayout):
    """Holds guesses"""

    def __init__(self, **kwargs):
        self.labels = {}
        super().__init__(**kwargs)
        for i in [7, 8, 9, 4, 5, 6, 1, 2, 3]:
            _label = Label(text=str(i),
                           color=TEXT_COLOR,
                           opacity=0)
            self.add_widget(_label)
            self.labels[i] = _label


class TileInput(TextInput):
    """Widget that allows setting values"""

    pat = re.compile('[^1-9]')

    num_codes = {
        (260, 'numpad4'): (-1, 0),
        (264, 'numpad8'): (0, 1),
        (262, 'numpad6'): (1, 0),
        (258, 'numpad2'): (0, -1),
    }
    codes = {
        (273, 'up'): (0, 1),
        (276, 'left'): (-1, 0),
        (274, 'down'): (0, -1),
        (275, 'right'): (1, 0),
    }

    app = None

    def __init__(self, **kwargs):
        self.locked = False
        if not self.app:
            self.app = App.get_running_app()
        super().__init__(**kwargs)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):

        if 'numlock' not in modifiers and keycode in self.num_codes.keys():
            key = self.num_codes[keycode]
            widget = self.parent.directional_focus[key]
            self.focus = False
            widget.input.focus = True

        elif 'shift' in modifiers and (keycode[0] in range(49, 58) or keycode[0] in range(257, 266)):
            value = keycode[1][-1]  # last digit of string
            guesses = self.parent.guesses
            label = guesses.labels[int(value)]
            _, r = divmod(label.opacity + 1, 2)
            label.opacity = r

        elif keycode in self.codes.keys():
            key = self.codes[keycode]
            widget = self.parent.directional_focus[key]
            self.focus = False
            widget.input.focus = True

        elif keycode == (13, 'enter'):
            return super().keyboard_on_key_down(window, (9, 'tab'), text, modifiers)

        # elif 'shift' in modifiers and keycode == (9, 'tab'):
        #     self.get_focus_previous()
        else:
            return super().keyboard_on_key_down(window, keycode, text, modifiers)

    def on_focus(self, _, value):
        if value:
            self.opacity = 1
            self.parent.label.opacity = 0
            self._trigger_guides()
        else:
            self.opacity = 0
            self.parent.label.opacity = 1

    def insert_text(self, substring, from_undo=False):
        pat = self.pat
        if len(self.text):
            self.text = ''
        s = re.sub(pat, '', substring)
        return super(TileInput, self).insert_text(s, from_undo=from_undo)

    def get_focus_next(self):
        tile = self.parent.get_focus_next()
        tile.input.focus = True

    def get_focus_previous(self):
        tile = self.parent.get_focus_previous()
        tile.input.focus = True

    def set_text(self, text):
        setattr(self.parent.label, 'text', text)
        if text:
            for label in self.parent.guesses.labels.values():
                label.opacity = 0
        conflicts = self.app.update_board(self.parent.grid_position, self.text)
        if conflicts:
            Tile.conflicts = conflicts
            for pos in conflicts:
                tile = Tile.tiles[pos]
                tile.label.color = .6, .1, .1, 1

    def _unbind_keyboard(self):
        self.set_text(self.text)
        super()._unbind_keyboard()

        if Tile.conflicts:
            print(Tile.conflicts)
            to_remove = {self.app.resolve_conflicts(pos) for pos in Tile.conflicts}
            for elem in to_remove:
                if elem in Tile.conflicts:
                    Tile.conflicts.remove(elem)

    def _trigger_guides(self):
        NineBy.instance.trigger_guides(self.parent.grid_position)


class TileLabel(Label):
    """Label displaying tiles' value"""


class BoxGuide(Label):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class LinearGuide(Label):

    def __init__(self, _, **kwargs):
        # self.pos_hint = (None, None)
        super().__init__(**kwargs)

    @classmethod
    def create_guide(cls, coord):
        new = cls(coord)
        cls.items[coord] = new
        return new


class ColGuide(LinearGuide):
    items = {}

    def __init__(self, num, **kwargs):
        super().__init__(None, **kwargs)
        self.col_pos = num


class RowGuide(LinearGuide):
    items = {}

    def __init__(self, num, **kwargs):
        super().__init__(None, **kwargs)
        self.row_pos = num


class ThreeBy(RelativeLayout):
    """3x3 grid of tiles"""

    def __init__(self, grid_pos, **kwargs):
        self.grid_pos = grid_pos
        self._h_offset, self._v_offset = 3 * grid_pos[0], 3 * grid_pos[1]
        super().__init__(**kwargs)

    def make_tiles(self, **_):
        for vert in range(3):
            for horiz in range(3):
                coords = (self._h_offset + horiz, self._v_offset + vert)

                tile = Tile(coords,
                            size_hint=(.33, .33),
                            pos_hint={'x': horiz / 3, 'y': vert / 3},
                            )

                self.add_widget(tile)

    def populate_tiles(self):
        app = App.get_running_app()
        for tile in self.children:
            try:
                value = app.board[tile.grid_position]
            except KeyError:
                value = None

            if value:
                tile.label.text = str(value)
                tile.label.underline = True

                tile.input.locked = True
                tile.input.disabled = True
                tile.locked = True


class NineBy(FloatLayout):
    """9x9 board containing 9 3x3 grids"""

    instance = None

    def __init__(self, **kw):
        super().__init__(**kw)
        NineBy.instance = self
        self.guides = False
        self.hint_size = 1 / 3 - .01
        self.offset = (1 / 3 - self.hint_size) * 2 / 3

        self.boxes = {}
        self.construct()
        self.rows = RowGuide.items
        self.cols = ColGuide.items

        for k, v in self.rows.items():
            print(k, v)

    def construct(self):
        self.add_linear_guides()
        self.add_box_guides()

        self.fill()
        for widget in self.children:
            try:
                widget.populate_tiles()
            except AttributeError:
                pass
        self.set_focus_behavior()

    def fill(self):

        def find_offset(n: int) -> float:
            return ((n * 1.0025 + 2 * self.offset) + 0.01 * (1 - n)) / 3

        for vert in range(3):
            for horiz in range(3):
                w = ThreeBy((horiz, vert))
                self.add_widget(w)
                w.make_tiles()
                w.size_hint = [self.hint_size for _ in range(2)]
                w.pos_hint = {'x': find_offset(horiz), 'y': find_offset(vert)}

    def set_focus_behavior(self):
        for grid in self.children:
            for tile in grid.children:
                tile.set_focus_behavior()

    def add_linear_guides(self):

        for index, cls in enumerate([RowGuide, ColGuide]):
            offset = 1 / 18
            width = (2 / 3 - self.hint_size) / 3

            if index == 0:
                size_hint = (1, width)
                delta = 'center_y'
                constant = 'center_x'
            else:
                size_hint = (width, 1)
                delta = 'center_x'
                constant = 'center_y'

            for i in range(3):
                for j in range(3):
                    _index = i * 3 + j
                    _offset = offset - j * (1 / 3 - self.hint_size) / 18
                    guide = cls.create_guide(_index)
                    guide.size_hint = size_hint
                    guide.pos_hint = {delta: _index / 9 + _offset, constant: .5}
                    guide.opacity = 0
                    self.add_widget(guide)

    def add_box_guides(self):
        width = (2 / 3 - self.hint_size) / 3

        for x in range(3):
            i, j, k = [x * 3 + _x for _x in range(3)]  # groups of 3 consecutive numbers
            for y in range(3):
                a, b, c = [y * 3 + _y for _y in range(3)]
                box = BoxGuide(size_hint=[width * 3 for _ in range(2)],
                               pos_hint={'x': a / 9 - (1 / 3 - self.hint_size) / 2,
                                         'y': i / 9 - (1 / 3 - self.hint_size) / 2},
                               # pos_hint={t:  a/9-(1/3-self.hint_size) for t in ['x', 'y']},
                               opacity=0,
                               )
                self.add_widget(box)
                for v in [i, j, k]:
                    for h in [a, b, c]:
                        self.boxes[h, v] = box

    def trigger_guides(self, pos: (int, int)):
        if self.guides:
            self._trigger_guides(pos)
        pass

    def _trigger_guides(self, pos):
        for row in self.rows.values():
            row.opacity = 0
        for col in self.cols.values():
            col.opacity = 0
        for box in self.boxes.values():
            box.opacity = 0

        row = self.rows[pos[1]]
        col = self.cols[pos[0]]
        box = self.boxes[pos]

        row.opacity = 1
        col.opacity = 1
        box.opacity = 1

    def guides_on(self):
        self.guides = True

    def guides_off(self):
        self.guides = False

        for row in self.rows.values():
            row.opacity = 0
        for col in self.cols.values():
            col.opacity = 0
        for box in self.boxes.values():
            box.opacity = 0


class Main(FloatLayout):
    """Main screen"""

    stop = threading.Event()

    def start_second_thread(self):
        threading.Thread(target=self.second_thread).start()

    def second_thread(self):
        Clock.schedule_once(self.start_test, 0)
        App.get_running_app().slow_solve()
        self.stop_test()

    def start_test(self, *args):
        print('Starting slow solve')

    @mainthread
    def stop_test(self):
        print('Solved!')
        for tile in Tile.tiles.values():
            tile.label.color = (.1, .6, .1, 1)

    @mainthread
    def update_values(self):
        app = App.get_running_app()
        board = app.board
        for pos, _tile in board.tiles.items():
            tile = Tile.tiles[pos]
            tile.label.text = str(_tile.value) if _tile.value else ''

    @staticmethod
    def puzzle_picker():
        PuzzlePicker.current = Factory.PuzzlePicker()
        PuzzlePicker.current.open()


class PuzzleRandomLayout(FloatLayout):
    """Layout for random choice options"""


class PuzzlePicker(Popup):
    """Popup for choosing puzzles"""

    current = None

    @staticmethod
    def random():
        return PuzzlePicker.current._random()

    @staticmethod
    def easy():
        return PuzzlePicker.current._random(difficulty='easy')

    @staticmethod
    def med():
        return PuzzlePicker.current._random(difficulty='medium')

    @staticmethod
    def hard():
        return PuzzlePicker.current._random(difficulty='hard')

    @staticmethod
    def _random(difficulty=None):
        app = App.get_running_app()
        puzzle = app.db.random_puzzle(difficulty)
        app.board = Board(puzzle=puzzle)
        NineBy.instance.children.clear()
        NineBy.instance.construct()
        PuzzlePicker.current.dismiss()


class SudokuSolverApp(App):
    # Config Properties

    dh_color = DARK_HIGHLIGHT
    dh_color_string = as_string(dh_color)
    dh_color_list = as_list(dh_color)

    bg_color = BACKGROUND_COLOR
    bg_color_string = as_string(bg_color)
    bg_color_list = as_list(bg_color)

    elem_color = ELEMENT_COLOR
    elem_color_string = as_string(elem_color)
    elem_color_list = as_list(elem_color)

    lh_color = LIGHT_HIGHLIGHT
    lh_color_string = as_string(lh_color)
    lh_color_list = as_list(lh_color)

    text_color = TEXT_COLOR
    text_color_string = as_string(text_color)
    text_color_list = as_list(text_color)

    # End Config properties
    # Begin Misc

    trans = (1, 1, 1, 0)
    trans_string = '1, 1, 1, 0'
    trans_list = [1, 1, 1, 0]

    hint_text_color = (0.6705882352941176, 0.6705882352941176, 0.6705882352941176, .1)
    board = {}
    tile_inputs = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.inspections = False
        self.solve_iter_count = 0
        self.db = Database()
        self.board = Board(puzzle=self.db.blank_puzzle)

    def build(self):
        return Main()

    def _set_board_value(self, pos, value):
        tile = self.board.tiles[pos]
        try:
            tile.value = int(value)
        except ValueError:
            tile.value = None
        return tile

    def update_board(self, pos, value):
        tile = self._set_board_value(pos, value)

        if self.inspections:
            return self.board.validate(tile)

    def resolve_conflicts(self, pos):
        tile = self.board.tiles[pos]
        conflicts = self.board.validate(tile)
        if not conflicts:
            print('not conflicts')
            label = Tile.tiles[pos].label
            label.color = self.text_color
            return pos

    def solve(self):
        self.board.solve()
        for pos, tile in self.board.tiles.items():
            val = tile.value
            Tile.tiles[pos].label.text = str(val)
            Tile.tiles[pos].label.color = (.1, .6, .1, 1)
            Tile.tiles[pos].input.text = str(val)

    def slow_solve(self):

        tiles = self.board.reset()
        self.solve_iter_count = 0
        self._slow_solve(tiles)
        print(self.solve_iter_count)

    def _slow_solve(self, tiles):

        tile = tiles.pop()
        label = Tile.tiles[tile.position].label
        label.color = (.1, .6, .1, 1)

        for i in range(1, 10):
            self.root.update_values()
            self.solve_iter_count += 1
            print(i)
            # time.sleep(.0001)
            tile.value = i

            if not self.board.validate(tile):
                label.color = self.text_color
                try:
                    x = self._slow_solve(tiles)
                except IndexError:  # Empty list
                    return True
                else:
                    if x:
                        return x
                    else:
                        label.color = (.1, .6, .1, 1)

        else:
            tile.value = None
            tiles.append(tile)

    def reset(self):
        self.board.reset()
        for pos, tile in self.board.tiles.items():
            val = tile.value
            Tile.tiles[pos].label.text = str(val) if val else ''
            Tile.tiles[pos].label.color = self.text_color
            Tile.tiles[pos].input.text = ''

    # def set_board(self, difficulty=None, uid=None):
    #     if uid:
    #         puzzle = self.db.all_puzzles[uid]
    #     elif difficulty:
    #         puzzle = self.db.random_puzzle()
    #     else:
    #         puzzle = self.db.blank_puzzle
    #
    #     self.board = Board(puzzle)
    #     self.reset()

    def on_stop(self):
        # The Kivy event loop is about to stop, set a stop signal;
        # otherwise the app window will close, but the Python process will
        # keep running until all secondary threads exit.
        self.root.stop.set()


if __name__ == '__main__':
    # Factory.register('PuzzlePicker', cls=PuzzlePicker)
    SudokuSolverApp().run()
