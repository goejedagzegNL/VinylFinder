
import sys
import sqlite3
import csv
import json
import re
import webbrowser

from pathlib import Path
from datetime import datetime
from urllib.parse import (
    quote_plus,
    urlencode,
    urlparse,
    urljoin,
    parse_qsl,
    urlunparse,
)

import requests
from bs4 import BeautifulSoup

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QLabel,
    QHeaderView,
    QAbstractItemView,
    QFileDialog,
    QProgressDialog,
)


APP_NAME = "VinylFinder"
APP_VERSION = "0.2.0"

DATA_DIR = Path.home() / "AppData" / "Local" / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "vinylfinder.db"

DEFAULT_SOURCES = [
    (
        "Discogs",
        "https://www.discogs.com/search/?{query_params}",
        1,
    ),
    (
        "eBay",
        "https://www.ebay.com/sch/i.html?{query_params}",
        1,
    ),
    (
        "Bandcamp",
        "https://bandcamp.com/search?q={query}",
        1,
    ),
]

ACTION_TERMS = (
    "toevoegen aan winkelwagen",
    "in winkelwagen",
    "winkelwagen",
    "add to cart",
    "add to bag",
    "buy now",
    "shop now",
    "checkout",
    "view cart",
    "view basket",
    "naar de kassa",
    "bestellen",
    "afrekenen",
    "verder winkelen",
    "login",
    "log in",
    "sign in",
    "register",
    "account",
    "search",
    "zoeken",
    "volgende",
    "previous",
    "next page",
    "add to wishlist",
    "toevoegen aan verlanglijst",
    "continue shopping",
    "proceed to checkout",
)

EXCLUDED_URL_PARTS = (
    "/search",
    "/zoeken",
    "/zoek/",
    "/account",
    "/cart",
    "/basket",
    "/winkelwagen",
    "/checkout",
    "/login",
    "/register",
    "/wishlist",
)

DIGITAL_TERMS = (
    "digital download",
    "mp3 download",
    "streaming only",
    "digital album",
    "download code",
    "instant download",
)


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url_template TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        count = conn.execute(
            "SELECT COUNT(*) FROM sources"
        ).fetchone()[0]

        if count == 0:
            conn.executemany(
                """
                INSERT INTO sources (name, url_template, enabled)
                VALUES (?, ?, ?)
                """,
                DEFAULT_SOURCES,
            )


def valid_http_url(url):
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme.lower() in ("http", "https")
            and bool(parsed.netloc)
        )
    except (ValueError, AttributeError):
        return False


def normalize(text):
    text = str(text or "").casefold()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def build_search_url(
    template,
    query,
    artist,
    title,
    album,
    year,
    record_format,
):
    values = {
        "query": quote_plus(query.strip()),
        "artist": quote_plus(artist.strip()),
        "title": quote_plus(title.strip()),
        "album": quote_plus(album.strip()),
        "year": quote_plus(year.strip()),
        "format": quote_plus(record_format.strip()),
        "query_params": urlencode({"q": query.strip()}),
    }

    try:
        result = template.format(**values)

        if not valid_http_url(result):
            return ""

        return result

    except (KeyError, ValueError, AttributeError):
        return ""


class SourceDialog(QDialog):
    def __init__(self, parent=None, source=None):
        super().__init__(parent)

        self.setWindowTitle("Website / Store")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://example.com/search?q={query}"
        )

        self.enabled_check = QCheckBox("Enable this source")
        self.enabled_check.setChecked(True)

        form.addRow("Name:", self.name_edit)
        form.addRow("Search URL template:", self.url_edit)
        form.addRow("", self.enabled_check)
        layout.addLayout(form)

        layout.addWidget(QLabel(
            "Available placeholders: {query}, {artist}, {title}, "
            "{album}, {year}, {format}, {query_params}."
        ))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if source:
            self.name_edit.setText(source["name"])
            self.url_edit.setText(source["url_template"])
            self.enabled_check.setChecked(bool(source["enabled"]))

    def validate_and_accept(self):
        name = self.name_edit.text().strip()
        template = self.url_edit.text().strip()

        if not name:
            QMessageBox.warning(
                self, "Missing name", "Enter a source name."
            )
            return

        test_url = template

        for key, value in {
            "{query}": "test",
            "{artist}": "artist",
            "{title}": "title",
            "{album}": "album",
            "{year}": "2020",
            "{format}": "vinyl",
            "{query_params}": "q=test",
        }.items():
            test_url = test_url.replace(key, value)

        if not valid_http_url(test_url):
            QMessageBox.warning(
                self,
                "Invalid URL",
                "Enter a valid HTTP or HTTPS URL template.",
            )
            return

        self.accept()

    def values(self):
        return (
            self.name_edit.text().strip(),
            self.url_edit.text().strip(),
            int(self.enabled_check.isChecked()),
        )


class VinylFinder(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(850, 560)
        self.showMaximized()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_search_tab(), "Search Records")
        self.tabs.addTab(self.create_sources_tab(), "Manage Sources")
        self.tabs.addTab(self.create_favorites_tab(), "Favorites")
        self.tabs.addTab(self.create_history_tab(), "Search History")

        self.setCentralWidget(self.tabs)

        self.refresh_sources()
        self.refresh_favorites()
        self.refresh_history()

        self.statusBar().showMessage(f"Database: {DB_PATH}")

    # ---------------------------------------------------------
    # SEARCH TAB
    # ---------------------------------------------------------

    def create_search_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()

        self.artist_edit = QLineEdit()
        self.title_edit = QLineEdit()
        self.album_edit = QLineEdit()
        self.label_edit = QLineEdit()
        self.catalog_edit = QLineEdit()
        self.year_edit = QLineEdit()

        self.year_edit.setPlaceholderText("e.g. 1977")

        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "Any vinyl format",
            "LP",
            "7-inch single",
            "10-inch",
            "12-inch single",
            "Box set",
        ])

        self.condition_combo = QComboBox()
        self.condition_combo.addItems([
            "Any condition",
            "New",
            "Near Mint",
            "Very Good Plus",
            "Very Good",
            "Good",
        ])

        self.min_price = QDoubleSpinBox()
        self.min_price.setRange(0, 100000)
        self.min_price.setPrefix("€ ")

        self.max_price = QDoubleSpinBox()
        self.max_price.setRange(0, 100000)
        self.max_price.setValue(100000)
        self.max_price.setPrefix("€ ")

        form.addRow("Artist:", self.artist_edit)
        form.addRow("Title:", self.title_edit)
        form.addRow("Album:", self.album_edit)
        form.addRow("Record label:", self.label_edit)
        form.addRow("Catalog number:", self.catalog_edit)
        form.addRow("Release year:", self.year_edit)
        form.addRow("Format:", self.format_combo)
        form.addRow("Condition:", self.condition_combo)

        price_row = QWidget()
        price_layout = QHBoxLayout(price_row)
        price_layout.setContentsMargins(0, 0, 0, 0)

        price_layout.addWidget(QLabel("Min:"))
        price_layout.addWidget(self.min_price)
        price_layout.addWidget(QLabel("Max:"))
        price_layout.addWidget(self.max_price)

        form.addRow("Price filter:", price_row)
        layout.addLayout(form)

        buttons = QHBoxLayout()

        search_btn = QPushButton("Search Enabled Sources")
        search_btn.clicked.connect(self.search_sources)

        products_btn = QPushButton("Search Products")
        products_btn.clicked.connect(self.search_products)

        clear_btn = QPushButton("Clear Filters")
        clear_btn.clicked.connect(self.clear_filters)

        buttons.addWidget(search_btn)
        buttons.addWidget(products_btn)
        buttons.addWidget(clear_btn)

        layout.addLayout(buttons)

        layout.addWidget(QLabel(
            "Search Enabled Sources opens store search pages. "
            "Search Products retrieves possible product listings."
        ))

        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels([
            "Website / Store",
            "Search URL",
            "Action",
        ])

        self.configure_table(self.results_table)
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.results_table, 1)

        layout.addWidget(QLabel("Found Products"))

        # No price column.
        self.product_table = QTableWidget(0, 3)
        self.product_table.setHorizontalHeaderLabels([
            "Website / Store",
            "Product",
            "Action",
        ])

        self.configure_table(self.product_table)
        self.product_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.product_table, 1)

        self.results_table.show()
        self.product_table.hide()

        return page

    @staticmethod
    def configure_table(table):
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )

    def current_query_parts(self):
        artist = self.artist_edit.text().strip()
        title = self.title_edit.text().strip()
        album = self.album_edit.text().strip()
        label = self.label_edit.text().strip()
        catalog = self.catalog_edit.text().strip()
        year = self.year_edit.text().strip()

        terms = [
            artist, title, album, label, catalog, year
        ]
        terms = [term for term in terms if term]

        record_format = self.format_combo.currentText()
        condition = self.condition_combo.currentText()

        if record_format != "Any vinyl format":
            terms.append(record_format)

        if condition != "Any condition":
            terms.append(condition)

        if self.min_price.value() > 0:
            terms.append(
                f"minimum price {self.min_price.value():.2f} EUR"
            )

        if self.max_price.value() < 100000:
            terms.append(
                f"maximum price {self.max_price.value():.2f} EUR"
            )

        return {
            "artist": artist,
            "title": title,
            "album": album,
            "label": label,
            "catalog": catalog,
            "year": year,
            "format": record_format,
            "query": " ".join(terms),
        }

    def enabled_sources(self):
        with connect_db() as conn:
            return conn.execute(
                "SELECT * FROM sources "
                "WHERE enabled = 1 ORDER BY name"
            ).fetchall()

    def record_search(self, query):
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO searches (query, created_at) "
                "VALUES (?, ?)",
                (
                    query,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

        self.refresh_history()

    def search_sources(self):
        parts = self.current_query_parts()

        if not parts["query"]:
            QMessageBox.information(
                self,
                "Search",
                "Enter at least an artist or title.",
            )
            return

        self.product_table.hide()
        self.results_table.show()
        self.results_table.setRowCount(0)

        self.record_search(parts["query"])

        for source in self.enabled_sources():
            url = build_search_url(
                source["url_template"],
                parts["query"],
                parts["artist"],
                parts["title"],
                parts["album"],
                parts["year"],
                    parts["format"],
            )

            if not valid_http_url(url):
                continue

            row = self.results_table.rowCount()
            self.results_table.insertRow(row)

            self.results_table.setItem(
                row, 0, QTableWidgetItem(source["name"])
            )

            url_item = QTableWidgetItem(url)
            url_item.setToolTip(url)
            self.results_table.setItem(row, 1, url_item)

            button = QPushButton("Open Search")
            button.clicked.connect(
                lambda checked=False, target=url:
                    webbrowser.open(target)
            )
            self.results_table.setCellWidget(row, 2, button)

        self.statusBar().showMessage(
            f"Prepared {self.results_table.rowCount()} search destinations."
        )

    # ---------------------------------------------------------
    # SEARCH PRODUCTS
    # ---------------------------------------------------------


    def search_products(self):
        parts = self.current_query_parts()

        # Verzamel alle ingevulde zoekvelden.
        search_keys = (
            "artist",
            "title",
            "album",
            "label",
            "catalog",
            "year",
        )

        terms = [
            parts.get(key, "").strip()
            for key in search_keys
            if parts.get(key, "").strip()
        ]

        record_format = self.format_combo.currentText()
        condition = self.condition_combo.currentText()

        if record_format != "Any vinyl format":
            terms.append(record_format)

        if condition != "Any condition":
            terms.append(condition)

        if not terms:
            QMessageBox.information(
                self,
                "Search Products",
                "Enter at least one search criterion.",
            )
            return

        query = " ".join(terms)

        # Toon de productresultaten en wis oude resultaten.
        self.results_table.hide()
        self.product_table.show()
        self.product_table.setRowCount(0)

        self.product_table.setColumnCount(3)
        self.product_table.setHorizontalHeaderLabels([
            "Website / Store",
            "Product",
            "Action",
        ])

        # Toon Searching... tijdens het voorbereiden.
        progress = QProgressDialog(
            "Searching...",
            "",
            0,
            0,
            self,
        )
        progress.setWindowTitle("VinylFinder")
        progress.setWindowModality(
            Qt.WindowModality.ApplicationModal
        )
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        QApplication.processEvents()

        try:
            # Discogs zonder API-token:
            # open de openbare zoekpagina in de browser.
            from urllib.parse import urlencode

            search_params = {
                "q": query,
                "type": "all",
            }

            # Gebruik Discogs' openbare zoekpagina.
            search_url = (
                "https://www.discogs.com/search/?"
                + urlencode(search_params)
            )

            if not valid_http_url(search_url):
                QMessageBox.warning(
                    self,
                    "Search Products",
                    "The Discogs search URL is invalid.",
                )
                return

            opened = webbrowser.open(search_url)

            if not opened:
                QMessageBox.warning(
                    self,
                    "Search Products",
                    "Could not open Discogs in your browser.",
                )
                return

            # Voeg Discogs als zoekbestemming toe.
            row = self.product_table.rowCount()
            self.product_table.insertRow(row)

            self.product_table.setItem(
                row,
                0,
                QTableWidgetItem("Discogs"),
            )

            self.product_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    f"Discogs search: {query}"
                ),
            )

            open_btn = QPushButton("Open Search")
            open_btn.clicked.connect(
                lambda checked=False, target=search_url:
                    webbrowser.open(target)
            )
            self.product_table.setCellWidget(
                row,
                2,
                open_btn,
            )

            self.record_search(query)

            self.statusBar().showMessage(
                "Discogs search opened in your browser."
            )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Search Products",
                f"Could not start the search:\n{exc}",
            )

        finally:
            # Sluit Searching... altijd, ook bij een fout.
            progress.close()
            progress.deleteLater()

        # Geen resultaten gevonden in de lokale producttabel?
        # De Discogs-zoekresultaten staan in de browser.
        if self.product_table.rowCount() == 0:
            QMessageBox.information(
                self,
                "Article Not Found",
                "No product result could be opened.\n\n"
                "Try different search criteria.",
            )

    # ---------------------------------------------------------
    # FILTERS
    # ---------------------------------------------------------

    def clear_filters(self):
        for widget in (
            self.artist_edit,
            self.title_edit,
            self.album_edit,
            self.label_edit,
            self.catalog_edit,
            self.year_edit,
        ):
            widget.clear()

        self.format_combo.setCurrentIndex(0)
        self.condition_combo.setCurrentIndex(0)
        self.min_price.setValue(0)
        self.max_price.setValue(100000)

        self.results_table.setRowCount(0)
        self.product_table.setRowCount(0)

        self.results_table.show()
        self.product_table.hide()

        self.statusBar().showMessage("Filters cleared.")

    # ---------------------------------------------------------
    # SOURCES
    # ---------------------------------------------------------

    def create_sources_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.sources_table = QTableWidget(0, 3)
        self.sources_table.setHorizontalHeaderLabels([
            "Name", "Search URL Template", "Enabled"
        ])
        self.configure_table(self.sources_table)
        self.sources_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.sources_table)

        buttons = QHBoxLayout()

        actions = [
            ("Add Source", self.add_source),
            ("Edit Selected", self.edit_source),
            ("Enable / Disable", self.toggle_source),
            ("Delete Selected", self.delete_source),
            ("Import CSV", self.import_sources_csv),
            ("Refresh", self.refresh_sources),
        ]

        for label, callback in actions:
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)

        layout.addLayout(buttons)
        return page

    def selected_source_id(self):
        row = self.sources_table.currentRow()

        if row < 0:
            return None

        item = self.sources_table.item(row, 0)

        return (
            item.data(Qt.ItemDataRole.UserRole)
            if item else None
        )

    def refresh_sources(self):
        if not hasattr(self, "sources_table"):
            return

        with connect_db() as conn:
            rows = conn.execute(
                "SELECT * FROM sources ORDER BY name"
            ).fetchall()

        self.sources_table.setRowCount(0)

        for source in rows:
            row = self.sources_table.rowCount()
            self.sources_table.insertRow(row)

            name_item = QTableWidgetItem(source["name"])
            name_item.setData(
                Qt.ItemDataRole.UserRole, source["id"]
            )

            self.sources_table.setItem(row, 0, name_item)
            self.sources_table.setItem(
                row, 1, QTableWidgetItem(source["url_template"])
            )
            self.sources_table.setItem(
                row, 2,
                QTableWidgetItem(
                    "Yes" if source["enabled"] else "No"
                ),
            )

    def add_source(self):
        dialog = SourceDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name, url, enabled = dialog.values()

        try:
            with connect_db() as conn:
                conn.execute(
                    "INSERT INTO sources "
                    "(name, url_template, enabled) VALUES (?, ?, ?)",
                    (name, url, enabled),
                )
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(
                self, "Source Error", str(exc)
            )
            return

        self.refresh_sources()

    def edit_source(self):
        source_id = self.selected_source_id()

        if source_id is None:
            QMessageBox.information(
                self, "Edit Source", "Select a source first."
            )
            return

        with connect_db() as conn:
            source = conn.execute(
                "SELECT * FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()

        if not source:
            return

        dialog = SourceDialog(self, source)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name, url, enabled = dialog.values()

        with connect_db() as conn:
            conn.execute(
                "UPDATE sources SET name=?, url_template=?, "
                "enabled=? WHERE id=?",
                (name, url, enabled, source_id),
            )

        self.refresh_sources()

    def toggle_source(self):
        source_id = self.selected_source_id()

        if source_id is None:
            QMessageBox.information(
                self, "Sources", "Select a source first."
            )
            return

        with connect_db() as conn:
            conn.execute(
                "UPDATE sources SET enabled = 1 - enabled "
                "WHERE id = ?",
                (source_id,),
            )

        self.refresh_sources()

    def delete_source(self):
        source_id = self.selected_source_id()

        if source_id is None:
            QMessageBox.information(
                self, "Sources", "Select a source first."
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Source",
            "Permanently remove the selected source?",
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        with connect_db() as conn:
            conn.execute(
                "DELETE FROM sources WHERE id = ?",
                (source_id,),
            )

        self.refresh_sources()

    def import_sources_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Sources from CSV",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )

        if not file_path:
            return

        imported = 0
        skipped = 0
        invalid = 0

        try:
            with open(
                file_path,
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as csv_file:
                sample = csv_file.read(4096)
                csv_file.seek(0)

                try:
                    dialect = csv.Sniffer().sniff(
                        sample, delimiters=",;\t"
                    )
                except csv.Error:
                    dialect = csv.excel

                reader = csv.DictReader(
                    csv_file, dialect=dialect
                )

                if not reader.fieldnames:
                    QMessageBox.warning(
                        self,
                        "CSV Import",
                        "The CSV file has no header row.",
                    )
                    return

                reader.fieldnames = [
                    (name or "").strip().lower()
                    for name in reader.fieldnames
                ]

                if not {"name", "url_template"}.issubset(
                    set(reader.fieldnames)
                ):
                    QMessageBox.warning(
                        self,
                        "CSV Import",
                        "Required columns: name, url_template. "
                        "Optional: enabled.",
                    )
                    return

                with connect_db() as conn:
                    for item in reader:
                        name = (
                            item.get("name") or ""
                        ).strip()
                        template = (
                            item.get("url_template") or ""
                        ).strip()

                        enabled_text = (
                            item.get("enabled") or "1"
                        ).strip().lower()

                        if not name or not template:
                            invalid += 1
                            continue

                        test_url = template

                        for key, value in {
                            "{query}": "test",
                            "{artist}": "artist",
                            "{title}": "title",
                            "{album}": "album",
                            "{year}": "2020",
                            "{format}": "vinyl",
                            "{query_params}": "q=test",
                        }.items():
                            test_url = test_url.replace(
                                key, value
                            )

                        if not valid_http_url(test_url):
                            invalid += 1
                            continue

                        if enabled_text in (
                            "1", "true", "yes", "enabled"
                        ):
                            enabled = 1
                        elif enabled_text in (
                            "0", "false", "no", "disabled"
                        ):
                            enabled = 0
                        else:
                            invalid += 1
                            continue

                        exists = conn.execute(
                            "SELECT 1 FROM sources "
                            "WHERE lower(name)=lower(?)",
                            (name,),
                        ).fetchone()

                        if exists:
                            skipped += 1
                            continue

                        conn.execute(
                            "INSERT INTO sources "
                            "(name, url_template, enabled) "
                            "VALUES (?, ?, ?)",
                            (name, template, enabled),
                        )

                        imported += 1

            self.refresh_sources()

            QMessageBox.information(
                self,
                "CSV Import Complete",
                f"Imported: {imported}\n"
                f"Skipped: {skipped}\n"
                f"Invalid rows: {invalid}",
            )

        except (OSError, csv.Error, UnicodeError) as exc:
            QMessageBox.critical(
                self,
                "CSV Import Failed",
                f"Could not import the CSV file:\n{exc}",
            )

    # ---------------------------------------------------------
    # FAVORITES
    # ---------------------------------------------------------

    def create_favorites_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.favorites_table = QTableWidget(0, 3)
        self.favorites_table.setHorizontalHeaderLabels([
            "Title", "URL", "Notes"
        ])
        self.configure_table(self.favorites_table)

        self.favorites_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.favorites_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )

        layout.addWidget(self.favorites_table)

        buttons = QHBoxLayout()

        open_btn = QPushButton("Open Selected URL")
        open_btn.clicked.connect(self.open_selected_favorite)

        delete_btn = QPushButton("Remove Favorite")
        delete_btn.clicked.connect(self.delete_favorite)

        add_btn = QPushButton("Add Current Product")
        add_btn.clicked.connect(self.add_current_favorite)

        buttons.addWidget(add_btn)
        buttons.addWidget(open_btn)
        buttons.addWidget(delete_btn)

        layout.addLayout(buttons)
        return page

    def refresh_favorites(self):
        if not hasattr(self, "favorites_table"):
            return

        with connect_db() as conn:
            rows = conn.execute(
                "SELECT * FROM favorites ORDER BY created_at DESC"
            ).fetchall()

        self.favorites_table.setRowCount(0)

        for fav in rows:
            row = self.favorites_table.rowCount()
            self.favorites_table.insertRow(row)

            title = QTableWidgetItem(fav["title"])
            title.setData(
                Qt.ItemDataRole.UserRole, fav["id"]
            )

            self.favorites_table.setItem(row, 0, title)
            self.favorites_table.setItem(
                row, 1, QTableWidgetItem(fav["url"])
            )
            self.favorites_table.setItem(
                row, 2, QTableWidgetItem(fav["notes"] or "")
            )

    def selected_favorite_id(self):
        row = self.favorites_table.currentRow()

        if row < 0:
            return None

        item = self.favorites_table.item(row, 0)

        return (
            item.data(Qt.ItemDataRole.UserRole)
            if item else None
        )

    def add_current_favorite(self):
        row = self.product_table.currentRow()

        if row < 0:
            QMessageBox.information(
                self,
                "Favorites",
                "Select a product in Found Products first.",
            )
            return

        source_item = self.product_table.item(row, 0)
        title_item = self.product_table.item(row, 1)
        button = self.product_table.cellWidget(row, 2)

        if not source_item or not title_item or not button:
            return

        # The Open Product button captures the target URL.
        # Store the URL explicitly on the button when adding results.
        product_url = getattr(button, "product_url", "")

        if not valid_http_url(product_url):
            QMessageBox.warning(
                self,
                "Favorites",
                "The selected product URL is unavailable.",
            )
            return

        try:
            with connect_db() as conn:
                conn.execute(
                    "INSERT INTO favorites "
                    "(title, url, notes, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        title_item.text(),
                        product_url,
                        source_item.text(),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
        except sqlite3.IntegrityError:
            QMessageBox.information(
                self,
                "Favorites",
                "This product is already a favorite.",
            )
            return

        self.refresh_favorites()

    def open_selected_favorite(self):
        row = self.favorites_table.currentRow()

        if row < 0:
            return

        item = self.favorites_table.item(row, 1)

        if item and valid_http_url(item.text()):
            webbrowser.open(item.text())

    def delete_favorite(self):
        fav_id = self.selected_favorite_id()

        if fav_id is None:
            QMessageBox.information(
                self,
                "Favorites",
                "Select a favorite first.",
            )
            return

        with connect_db() as conn:
            conn.execute(
                "DELETE FROM favorites WHERE id = ?",
                (fav_id,),
            )

        self.refresh_favorites()

    # ---------------------------------------------------------
    # SEARCH HISTORY
    # ---------------------------------------------------------

    def create_history_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.history_table = QTableWidget(0, 2)
        self.history_table.setHorizontalHeaderLabels([
            "Search Query", "Date / Time"
        ])
        self.configure_table(self.history_table)
        self.history_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )

        layout.addWidget(self.history_table)

        buttons = QHBoxLayout()

        repeat_btn = QPushButton("Repeat Selected Search")
        repeat_btn.clicked.connect(self.repeat_history_search)

        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self.clear_history)

        buttons.addWidget(repeat_btn)
        buttons.addWidget(clear_btn)

        layout.addLayout(buttons)
        return page

    def refresh_history(self):
        if not hasattr(self, "history_table"):
            return

        with connect_db() as conn:
            rows = conn.execute(
                "SELECT * FROM searches ORDER BY id DESC LIMIT 500"
            ).fetchall()

        self.history_table.setRowCount(0)

        for item in rows:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            query_item = QTableWidgetItem(item["query"])
            query_item.setData(
                Qt.ItemDataRole.UserRole, item["id"]
            )

            self.history_table.setItem(row, 0, query_item)
            self.history_table.setItem(
                row, 1, QTableWidgetItem(item["created_at"])
            )

    def repeat_history_search(self):
        row = self.history_table.currentRow()

        if row < 0:
            QMessageBox.information(
                self,
                "Search History",
                "Select a search first.",
            )
            return

        item = self.history_table.item(row, 0)

        if not item:
            return

        query = item.text()
        self.clear_filters()
        self.artist_edit.setText(query)
        self.tabs.setCurrentIndex(0)
        self.search_sources()

    def clear_history(self):
        answer = QMessageBox.question(
            self,
            "Clear History",
            "Delete all saved search history?",
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        with connect_db() as conn:
            conn.execute("DELETE FROM searches")

        self.refresh_history()


def main():
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    window = VinylFinder()
    window.showMaximized()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
