
import sys
import sqlite3
import csv
import requests
import webbrowser
import re
from pathlib import Path
from urllib.parse import quote_plus, urlencode, urlparse, urljoin
from datetime import datetime
from bs4 import BeautifulSoup

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QMessageBox, QDialog,
    QDialogButtonBox, QCheckBox, QLabel, QHeaderView, QAbstractItemView,
    QSplitter, QFileDialog
)

APP_NAME = "VinylFinder"
APP_VERSION = "0.1.0"

# Keep user data outside the executable's installation directory.
DATA_DIR = Path.home() / "AppData" / "Local" / "VinylFinder"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "vinylfinder.db"


DEFAULT_SOURCES = [
    ("Discogs", "https://www.discogs.com/search/?{query_params}", 1),
    ("eBay", "https://www.ebay.com/sch/i.html?{query_params}", 1),
    ("Bandcamp", "https://bandcamp.com/search?q={query}", 1),
]

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

        count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
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
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False



def build_search_url(
    template, query, artist, title, album, year, record_format
):
    """Build a URL from a source template.

    Supported placeholders:
    {query}, {artist}, {title}, {album}, {year}, {format}, {query_params}
    """
    from urllib.parse import quote_plus, urlencode

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
        url = template.format(**values)
        if not url.startswith(("https://", "http://")):
            return ""
        return url
    except (KeyError, ValueError):
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
            "Use {query}, {artist}, {album}, {year}, {format} or {query_params} "
            "in the URL. The source must support the chosen URL format."
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
        url = self.url_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Missing name", "Enter a source name.")
            return
        if not valid_http_url(url.replace("{query}", "test")
                              .replace("{artist}", "test")
                              .replace("{album}", "test")
                              .replace("{year}", "2020")
                              .replace("{format}", "vinyl")
                              .replace("{query_params}", "q=test")):
            QMessageBox.warning(
                self, "Invalid URL",
                "Enter a valid HTTP or HTTPS search URL."
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
        self.resize(1120, 720)
        self.setMinimumSize(850, 560)

        tabs = QTabWidget()
        tabs.addTab(self.create_search_tab(), "Search Records")
        tabs.addTab(self.create_sources_tab(), "Manage Sources")
        tabs.addTab(self.create_favorites_tab(), "Favorites")
        tabs.addTab(self.create_history_tab(), "Search History")
        self.setCentralWidget(tabs)
        self.tabs = tabs

        self.refresh_sources()
        self.refresh_favorites()
        self.refresh_history()

        self.statusBar().showMessage(
            f"Local database: {DB_PATH}"
        )

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
            "Any vinyl format", "LP", "7-inch single", "10-inch",
            "12-inch single", "Box set"
        ])

        self.condition_combo = QComboBox()
        self.condition_combo.addItems([
            "Any condition", "New", "Near Mint", "Very Good Plus",
            "Very Good", "Good"
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
        form.addRow("Price range:", price_row)

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
            "Search Products attempts to retrieve matching product listings."
        ))

        
        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(
            ["Website / Store", "Search URL", "Action"]
        )
        self.results_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.results_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.results_table, 1)
        
        layout.addWidget(QLabel("Found Products"))

        self.product_table = QTableWidget(0, 4)
        self.product_table.setHorizontalHeaderLabels([
            "Website / Store",
            "Product",
            "Price",
            "Action",
        ])
        self.product_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.product_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.product_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.product_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.product_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.product_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.product_table, 1)
        self.results_table.show()
        self.product_table.hide()
        
        return page

    def create_sources_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.sources_table = QTableWidget(0, 3)
        self.sources_table.setHorizontalHeaderLabels(
            ["Name", "Search URL Template", "Enabled"]
        )
        self.sources_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.sources_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.sources_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.sources_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.sources_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.sources_table)

        buttons = QHBoxLayout()

        add_btn = QPushButton("Add Source")
        edit_btn = QPushButton("Edit Selected")
        toggle_btn = QPushButton("Enable / Disable")
        delete_btn = QPushButton("Delete Selected")
        import_btn = QPushButton("Import CSV")
        refresh_btn = QPushButton("Refresh")

        add_btn.clicked.connect(self.add_source)
        edit_btn.clicked.connect(self.edit_source)
        toggle_btn.clicked.connect(self.toggle_source)
        delete_btn.clicked.connect(self.delete_source)
        import_btn.clicked.connect(self.import_sources_csv)
        refresh_btn.clicked.connect(self.refresh_sources)

        for button in (
            add_btn, edit_btn, toggle_btn, delete_btn,
            import_btn, refresh_btn
        ):
            buttons.addWidget(button)

        layout.addLayout(buttons)
        return page

    def create_favorites_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.favorites_table = QTableWidget(0, 3)
        self.favorites_table.setHorizontalHeaderLabels(
            ["Title", "URL", "Notes"]
        )
        self.favorites_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.favorites_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.favorites_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.favorites_table)

        buttons = QHBoxLayout()
        open_btn = QPushButton("Open Selected URL")
        delete_btn = QPushButton("Remove Favorite")
        open_btn.clicked.connect(self.open_selected_favorite)
        delete_btn.clicked.connect(self.delete_favorite)
        buttons.addWidget(open_btn)
        buttons.addWidget(delete_btn)
        layout.addLayout(buttons)
        return page

    def create_history_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.history_table = QTableWidget(0, 2)
        self.history_table.setHorizontalHeaderLabels(
            ["Search Query", "Date / Time"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.history_table)

        buttons = QHBoxLayout()
        repeat_btn = QPushButton("Repeat Selected Search")
        clear_btn = QPushButton("Clear History")
        repeat_btn.clicked.connect(self.repeat_history_search)
        clear_btn.clicked.connect(self.clear_history)
        buttons.addWidget(repeat_btn)
        buttons.addWidget(clear_btn)
        layout.addLayout(buttons)
        return page

   
    def current_query_parts(self):
        artist = self.artist_edit.text().strip()
        title = self.title_edit.text().strip()
        album = self.album_edit.text().strip()
        label = self.label_edit.text().strip()
        catalog = self.catalog_edit.text().strip()
        year = self.year_edit.text().strip()

        terms = [artist, title, album, label, catalog, year]
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
  
    def search_sources(self):
        parts = self.current_query_parts()
        self.product_table.hide()
        self.results_table.show()
        self.results_table.setRowCount(0)
        
        if not parts["query"]:
            QMessageBox.information(
                self, "Search", "Enter at least an artist or title."
            )
            return

        with connect_db() as conn:
            conn.execute(
                "INSERT INTO searches (query, created_at) VALUES (?, ?)",
                (parts["query"], datetime.now().isoformat(timespec="seconds")),
            )

        with connect_db() as conn:
            sources = conn.execute(
                "SELECT * FROM sources WHERE enabled = 1 ORDER BY name"
            ).fetchall()

        self.results_table.setRowCount(0)

        for source in sources:
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

            open_btn = QPushButton("Open Search")
            open_btn.clicked.connect(
                lambda checked=False, target=url: webbrowser.open(target)
            )
            self.results_table.setCellWidget(row, 2, open_btn)

        self.refresh_history()
        self.statusBar().showMessage(
            f"Prepared {self.results_table.rowCount()} search destinations."
        )

        
    def search_products(self):
        parts = self.current_query_parts()

        if not any(
            parts.get(key, "").strip()
            for key in ("artist", "title", "album")
        ):
            QMessageBox.information(
                self,
                "Search Products",
                "Enter an artist, title or album first.",
            )
            return
         
        self.results_table.hide()
        self.product_table.show()
        self.product_table.setRowCount(0)
        self.statusBar().showMessage("Searching enabled stores...")
        QApplication.processEvents()

        with connect_db() as conn:
            sources = conn.execute(
                "SELECT * FROM sources WHERE enabled = 1 ORDER BY name"
            ).fetchall()

        terms = [
            parts.get(key, "").strip().casefold()
            for key in ("artist", "title", "album")
            if parts.get(key, "").strip()
        ]

        found = 0
        failed = []

        for source in sources:
            url = build_search_url(
                source["url_template"],
                parts["query"],
                parts["artist"],
                parts.get("title", ""),
                parts["album"],
                parts["year"],
                parts["format"],
            )

            if not valid_http_url(url):
                failed.append(source["name"])
                continue

            try:
                response = requests.get(
                    url,
                    timeout=15,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
                        )
                    },
                )
                response.raise_for_status()

                if "html" not in response.headers.get(
                    "Content-Type", ""
                ).lower():
                    failed.append(source["name"])
                    continue

                soup = BeautifulSoup(response.text, "html.parser")

                for link in soup.find_all("a", href=True):
                    
                    title_text = " ".join(link.stripped_strings).strip()

                    # Negeer lege links en teksten die geen productnamen zijn.
                    if len(title_text) < 5:
                         continue
                      
                    # Negeer veelvoorkomende website-acties en navigatielinks.
                    action_terms = (
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
                    )

                    normalized_title = title_text.casefold().strip()

                    if any(term in normalized_title for term in action_terms):
                        continue
                    
                    parent = link.parent
                    context = (
                        parent.get_text(" ", strip=True)
                        if parent else title_text
                    )
                    searchable = (title_text + " " + context).casefold()

                    if not all(term in searchable for term in terms):
                        continue

                    product_url = urljoin(url, link["href"])

                    if not valid_http_url(product_url):
                        continue

                    if any(
                        part in product_url.casefold()
                        for part in (
                            "/search", "/zoek/", "/account",
                            "/cart", "/winkelwagen", "/login",
                        )
                    ):
                        continue

                    if product_url.rstrip("/") == url.rstrip("/"):
                        continue

                    digital_terms = (
                        "digital download", "mp3 download",
                        "streaming only", "digital album",
                    )
                    if any(term in searchable for term in digital_terms):
                        continue

                    row = self.product_table.rowCount()
                    self.product_table.insertRow(row)

                    self.product_table.setItem(
                        row, 0, QTableWidgetItem(source["name"])
                    )
                    self.product_table.setItem(
                        row, 1, QTableWidgetItem(title_text)
                    )
                    price_match = re.search(
                        r"(?:€\s*|EUR\s*|USD\s*|\$\s*|£\s*)"
                        r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"
                        r"|"
                        r"\d+(?:[.,]\d{2})?\s*(?:EUR|USD)",
                        context,
                        re.IGNORECASE,
                    )

                    price = price_match.group(0).strip() if price_match else "Unknown"

                    price = (
                        price_match.group(0)
                        if price_match else "Unknown"
                    )
                    self.product_table.setItem(
                        row, 2, QTableWidgetItem(price)
                    )

                    
                    open_btn = QPushButton("Open Product")
                    open_btn.clicked.connect(
                        lambda checked=False, target=product_url:
                            webbrowser.open(target)
                    )
                    self.product_table.setCellWidget(row, 3, open_btn)
                    found += 1
            
            
            except requests.RequestException:
                failed.append(source["name"])

        self.statusBar().showMessage(
            f"Found {found} possible product results."
        )

        if failed:
            QMessageBox.information(
                self,
                "Some stores could not be searched",
                "Automatic retrieval failed for:\n"
                + "\n".join(failed)
                + "\n\nSome stores may block automated requests.",
            )

        if found == 0:
            QMessageBox.information(
                self,
                "No matching products",
                "No matching product links were identified. "
                "This does not prove that the stores have no stock.",
            )


    
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
         
    def selected_source_id(self):
        row = self.sources_table.currentRow()
        if row < 0:
            return None
        item = self.sources_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

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
            name_item.setData(Qt.ItemDataRole.UserRole, source["id"])
            self.sources_table.setItem(row, 0, name_item)
            self.sources_table.setItem(
                row, 1, QTableWidgetItem(source["url_template"])
            )
            self.sources_table.setItem(
                row, 2, QTableWidgetItem(
                    "Yes" if source["enabled"] else "No"
                )
            )


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

                reader = csv.DictReader(csv_file, dialect=dialect)

                if not reader.fieldnames:
                    QMessageBox.warning(
                        self,
                        "CSV Import",
                        "The CSV file is empty or has no header row.",
                    )
                    return

                reader.fieldnames = [
                    (name or "").strip().lower()
                    for name in reader.fieldnames
                ]

                required = {"name", "url_template"}
                if not required.issubset(set(reader.fieldnames)):
                    QMessageBox.warning(
                        self,
                        "CSV Import",
                        "Required columns: name, url_template. "
                        "Optional column: enabled.",
                    )
                    return

                with connect_db() as conn:
                    for row in reader:
                        name = (row.get("name") or "").strip()
                        template = (
                            row.get("url_template") or ""
                        ).strip()

                        enabled_text = (
                            row.get("enabled") or "1"
                        ).strip().lower()

                        if not name or not template:
                            invalid += 1
                            continue

                        test_url = template
                        for placeholder, replacement in (
                            ("{query}", "test"),
                            ("{artist}", "artist"),
                            ("{title}", "title"),
                            ("{album}", "album"),
                            ("{year}", "2020"),
                            ("{format}", "vinyl"),
                            ("{query_params}", "q=test"),
                        ):
                            test_url = test_url.replace(
                                placeholder, replacement
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
                            "WHERE lower(name) = lower(?)",
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
                f"Skipped (duplicate names): {skipped}\n"
                f"Invalid rows: {invalid}",
            )

        except (OSError, csv.Error, UnicodeError) as exc:
            QMessageBox.critical(
                self,
                "CSV Import Failed",
                f"Could not import the CSV file:\n{exc}",
            )
    
    def add_source(self):
        dialog = SourceDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, url, enabled = dialog.values()
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO sources (name, url_template, enabled) "
                "VALUES (?, ?, ?)", (name, url, enabled)
            )
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
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        if not source:
            return

        dialog = SourceDialog(self, source)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, url, enabled = dialog.values()
        with connect_db() as conn:
            conn.execute(
                "UPDATE sources SET name=?, url_template=?, enabled=? "
                "WHERE id=?", (name, url, enabled, source_id)
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
                "UPDATE sources SET enabled = 1 - enabled WHERE id = ?",
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
            self, "Delete Source",
            "Permanently remove the selected source?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with connect_db() as conn:
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        self.refresh_sources()

    def selected_favorite_id(self):
        row = self.favorites_table.currentRow()
        if row < 0:
            return None
        item = self.favorites_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

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
            title.setData(Qt.ItemDataRole.UserRole, fav["id"])
            self.favorites_table.setItem(row, 0, title)
            self.favorites_table.setItem(row, 1, QTableWidgetItem(fav["url"]))
            self.favorites_table.setItem(
                row, 2, QTableWidgetItem(fav["notes"] or "")
            )

    def open_selected_favorite(self):
        row = self.favorites_table.currentRow()
        if row < 0:
            return
        url_item = self.favorites_table.item(row, 1)
        if url_item and valid_http_url(url_item.text()):
            webbrowser.open(url_item.text())

    def delete_favorite(self):
        fav_id = self.selected_favorite_id()
        if fav_id is None:
            QMessageBox.information(
                self, "Favorites", "Select a favorite first."
            )
            return
        with connect_db() as conn:
            conn.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))
        self.refresh_favorites()

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
            query_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            self.history_table.setItem(row, 0, query_item)
            self.history_table.setItem(
                row, 1, QTableWidgetItem(item["created_at"])
            )

    def repeat_history_search(self):
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Search History", "Select a search first."
            )
            return
        query = self.history_table.item(row, 0).text()
        self.clear_filters()
        self.artist_edit.setText(query)
        self.tabs.setCurrentIndex(0)
        self.search_sources()

    def clear_history(self):
        answer = QMessageBox.question(
            self, "Clear History",
            "Delete all saved search history?"
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
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
