"""
Visual part of the project. May have memory leak, since some sub-element are not deleted explicitly set to delete.
"""
import json
import sys
import tempfile
import warnings

from sqlite3 import Connection
from typing import Optional, Dict, List, Set

from PySide6.QtCore import Slot, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QWidget, QHBoxLayout, QVBoxLayout, QTreeWidget,
    QTreeWidgetItem, QGridLayout, QLabel
)

from back import get_flag_dict, search_saves, get_flags, \
    search_saves_where_tags, get_tags_header, get_tags_dict


def get_rgb_from_hex(code):
    code_hex = code.replace("#", "")
    rgb = tuple(int(code_hex[i:i + 2], 16) for i in (0, 2, 4))
    return QColor.fromRgb(rgb[0], rgb[1], rgb[2])


class AutoHideButton(QPushButton):
    was_clicked = Signal(QPushButton)

    def __init__(self, text, tag_id: str, parent=None):
        super().__init__(text, parent)
        self.clicked.connect(self.on_clicked)
        self.tag_id = tag_id

    @Slot()
    def on_clicked(self):
        self.hide()
        self.was_clicked.emit(self)


class LegendWidget(QWidget):
    tag_filter = Signal(str)

    def __init__(self,
                 parent: Optional[QWidget] = None,
                 *args,
                 **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tag_tree = QTreeWidget(self)  # placeholder
        self.tag_tree.setHeaderLabel("Tags filtering")
        layout.addWidget(self.tag_tree)
        self.tag_tree.itemClicked.connect(self.on_item_clicked)
        self.tag_tree.hideColumn(1)
        self.setLayout(layout)

    def get_tree_items(self, tag_dict, color_map: Dict) -> List[QTreeWidgetItem]:
        """

        :param tag_dict:
        :param color_map:
        :return:
        """
        items = []
        for top_tag_id, top_tag_dict in tag_dict.items():
            item = QTreeWidgetItem([top_tag_dict["display"], top_tag_id])
            item.setBackground(0, get_rgb_from_hex(color_map[top_tag_id]["color"]))
            for subchild_item in self.get_tree_items(top_tag_dict["childs"], color_map):
                item.addChild(subchild_item)
            items.append(item)

        return items

    def update_tree(self, tag_dict: Dict, color_map: Dict) -> None:
        """

        :param tag_dict:
        :param color_map:
        :return:
        """
        items = self.get_tree_items(tag_dict, color_map)
        self.tag_tree.insertTopLevelItems(0, items)

    def on_item_clicked(self, item, column):
        """

        :param item:
        :param column:
        :return:
        """
        self.tag_filter.emit(item.text(1))


class BannerWidget(QWidget):
    filter = Signal(str)

    def __init__(self,
                 parent: Optional[QWidget] = None,
                 *args,
                 **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Search something...")
        self.filter_edit.textEdited.connect(self.text_filter_changed)
        layout.addWidget(self.filter_edit)
        self.setLayout(layout)

    @Slot(str)
    def text_filter_changed(self, text: str):
        """Emit the text filter string"""
        self.filter.emit(text)


class TagFilterWidget(QWidget):
    filter_changed = Signal(set)
    display_changed = Signal(set)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.tag_buttons = {}
        self.selected_tag = set()
        self.tag_group_buttons = {}
        self.displayed_tag = set()
        self._init_ui()

    def update_buttons(self, tag_dict: Dict, color_map: Dict):
        """

        :param tag_dict:
        :param color_map:
        :return:
        """
        for tag_id, tag_subdict in tag_dict.items():
            if len(tag_subdict["childs"]) == 0:
                self.tag_buttons[tag_id] = AutoHideButton(tag_subdict["display"], tag_id, self)
                self.tag_buttons[tag_id].was_clicked.connect(self.remove_button)
                self.tag_buttons[tag_id].setStyleSheet(f"background-color: {color_map[tag_id]['color']};")
                self.tag_buttons[tag_id].hide()
            else:
                self.tag_group_buttons[tag_id] = AutoHideButton(tag_subdict["display"], tag_id, self)
                self.tag_group_buttons[tag_id].was_clicked.connect(self.remove_button)
                self.tag_group_buttons[tag_id].setStyleSheet(
                    f"background-color: {color_map[tag_id]['color']};")
                self.tag_group_buttons[tag_id].hide()
                self.update_buttons(tag_subdict["childs"], color_map)

    def _init_ui(self) -> None:
        """

        :return:
        """
        self.top_panel = QWidget(self)
        self.top_panel.setLayout(QGridLayout())
        self.bottom_panel = QWidget(self)
        self.bottom_panel.setLayout(QGridLayout())
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("Filtered tag", self))
        self.layout.addWidget(self.top_panel)
        self.layout.addWidget(QLabel("Displayed tag collection", self))
        self.layout.addWidget(self.bottom_panel)

        self.setLayout(self.layout)

    @Slot(str)
    def add_button(self, tag_id: str):
        if tag_id in self.tag_buttons:
            if self.top_panel.layout().indexOf(self.tag_buttons[tag_id]) == -1:
                self.top_panel.layout().addWidget(self.tag_buttons[tag_id])
                self.tag_buttons[tag_id].show()
                self.selected_tag.add(self.tag_buttons[tag_id].text())
                self.filter_changed.emit(self.selected_tag)
        elif tag_id in self.tag_group_buttons:
            if self.bottom_panel.layout().indexOf(self.tag_group_buttons[tag_id]) == -1:
                self.bottom_panel.layout().addWidget(self.tag_group_buttons[tag_id])
                self.tag_group_buttons[tag_id].show()
                self.displayed_tag.add(tag_id)
                self.display_changed.emit(self.displayed_tag)
        else:
            warnings.warn(f"No tag id found {tag_id}")

    def remove_button(self, button: AutoHideButton):
        """

        :param button:
        :return:
        """
        if self.top_panel.layout().indexOf(button) != -1:
            self.top_panel.layout().removeWidget(button)
            self.selected_tag.remove(button.text())
            self.filter_changed.emit(self.selected_tag)
        else:
            self.bottom_panel.layout().removeWidget(button)
            self.displayed_tag.remove(button.tag_id)
            self.display_changed.emit(self.displayed_tag)


class MultiColorWidget(QWidget):
    def __init__(self, data_flag, color_map, parent=None):
        super().__init__(parent)
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(0)
        for flag in data_flag:
            label = QLabel(color_map[flag]["display"])
            label.setStyleSheet(
                f"background-color: {color_map[flag]['color']};")
            layout.addWidget(label)  # may change this

        self.setLayout(layout)


class SaveTableWidget(QTableWidget):
    def __init__(self, parent: Optional[QWidget] = None,
                 color_map: Dict = None,
                 *args,
                 **kwargs) -> None:
        super().__init__(parent=parent, *args, **kwargs)

        self.color_map = color_map
        self.setColumnCount(2)
        self.setColumnWidth(0, 5*self.columnWidth(1))
        self.displayed_tags = set()
        self._cache = None

    def clear_table(self):
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.takeItem(row, col)
                widget = self.cellWidget(row, col)
                if item:
                    del item
                if widget:
                    widget.deleteLater()
        self.clear()
    @Slot(dict)
    def display_save_tag(self,
                         save_tag_dict: Dict[str, Dict[str, str]] = None) -> None:
        """

        :param save_tag_dict:
        :return:
        """
        self.clear_table()
        self.setHorizontalHeaderLabels(["Path", "Tags"])
        if save_tag_dict is None:
            save_tag_dict = self._cache
        self.setRowCount(len(save_tag_dict))
        for index_, (key, value) in enumerate(save_tag_dict.items()):
            save_path_item = QTableWidgetItem(value["location"])
            self.setItem(index_, 0, save_path_item)
            if len(self.displayed_tags) == 0:
                flags = MultiColorWidget(value["flags"], self.color_map, self)
            else:
                relevant_color = [self.color_map[color]['color'] for color in self.displayed_tags]
                flags = MultiColorWidget(
                    [flag for flag in value["flags"] if self.color_map[flag]['color'] in relevant_color],
                    self.color_map, self)
            self.setCellWidget(index_, 1, flags)
        self.resizeRowsToContents()
        self._cache = save_tag_dict
    @Slot(set)
    def display_update(self, save_tag_set: Set[str]) -> None:
        """

        :param save_tag_set:
        :return:
        """
        self.displayed_tags = save_tag_set
        self.display_save_tag()

class MainWindow(QWidget):
    """The main display windows for the application."""

    connection: Connection

    update_table = Signal(dict)

    def __init__(self):
        super().__init__()

        self.temp_dir = tempfile.TemporaryDirectory()
        self._init_database()
        self._init_color_map()
        self._init_ui()
        self._init_filter()
        self.update_display()
        QApplication.instance().aboutToQuit.connect(self.cleanup)

    def _init_filter(self):
        """Initialize the filter requests."""
        self.tag_filter: Set[str] = set()
        self.text_filter = None

    def update_display(self) -> None:
        """

        :return:
        """
        if len(self.tag_filter) > 0:
            save_iterable = search_saves_where_tags(self.connection,
                                                    tuple(self.tag_filter),
                                                    self.text_filter)
        else:
            save_iterable = search_saves(self.connection, self.text_filter)
        self.update_table.emit(get_flags(save_iterable, self.connection))

    def _init_database(self):
        """Generate the database for searching.
        Note: no cache...
        """
        self.connection = get_flag_dict(self.temp_dir.name)

    def _init_ui(self):
        """"""
        self.legend_widget = LegendWidget(self)

        tag_dict = get_tags_dict(self.connection)
        layout = QHBoxLayout()
        layout.addWidget(self.legend_widget)

        central_widget = QWidget(self)
        layout.addWidget(central_widget)

        central_layout = QVBoxLayout()
        self.top_banner_widget = BannerWidget(self)
        self.legend_widget.update_tree(tag_dict, self.color_map)

        self.left_filter_widget = TagFilterWidget(self)
        self.left_filter_widget.update_buttons(tag_dict, self.color_map)
        self.legend_widget.tag_filter.connect(
            self.left_filter_widget.add_button)

        self.save_table_widget = SaveTableWidget(self, self.color_map)
        self.update_table.connect(self.save_table_widget.display_save_tag)

        self.top_banner_widget.filter.connect(self.update_filter)

        self.left_filter_widget.filter_changed.connect(self.update_tag_filter)
        self.left_filter_widget.display_changed.connect(self.save_table_widget.display_update)

        central_layout.addWidget(self.top_banner_widget)
        central_layout.addWidget(self.save_table_widget)
        central_widget.setLayout(central_layout)

        layout.addWidget(self.left_filter_widget)
        layout.setStretch(0, 1)
        layout.setStretch(1, 5)
        layout.setStretch(2, 1)
        self.setLayout(layout)

    def _init_color_map(self):
        """Need to change this for custom values."""
        tag_header = get_tags_header(self.connection)
        with open("color.json") as color_config_file:
            color_map = json.load(color_config_file)
        for tag_name in tag_header:
            tag_header[tag_name]["color"] = color_map.get(tag_header[tag_name]["top_parent"])

        self.color_map = tag_header

    @Slot(str)
    def update_filter(self, filter_text: str) -> None:
        self.text_filter = filter_text if len(filter_text) > 0 else None
        self.update_display()

    @Slot(list)
    def update_tag_filter(self, tag_filter: Set[str]) -> None:
        self.tag_filter = tag_filter
        self.update_display()

    @Slot()
    def cleanup(self):
        """Clean the folder where the temporary database was created."""
        self.connection.close()
        self.temp_dir.cleanup()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.resize(1024, 768)
    main_window.show()
    sys.exit(app.exec())
