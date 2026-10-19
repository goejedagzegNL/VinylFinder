import sys
import sqlite3
import csv
import re
import webbrowser
import urllib.request
import urllib.error
from html.parser import HTMLParser

from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus, urlencode, urlparse, parse_qs, unquote

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
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
APP_VERSION = "0.5.0"

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


# Europese landen voor de landenkeuzelijst. De landcode wordt ook gebruikt
# om waar mogelijk een lokale eBay-site te selecteren.
EUROPEAN_COUNTRIES = [
    ("Albania", "AL"), ("Andorra", "AD"), ("Armenia", "AM"),
    ("Austria", "AT"), ("Azerbaijan", "AZ"), ("Belarus", "BY"),
    ("Belgium", "BE"), ("Bosnia and Herzegovina", "BA"),
    ("Bulgaria", "BG"), ("Croatia", "HR"), ("Cyprus", "CY"),
    ("Czechia", "CZ"), ("Denmark", "DK"), ("Estonia", "EE"),
    ("Finland", "FI"), ("France", "FR"), ("Georgia", "GE"),
    ("Germany", "DE"), ("Greece", "GR"), ("Hungary", "HU"),
    ("Iceland", "IS"), ("Ireland", "IE"), ("Italy", "IT"),
    ("Kosovo", "XK"), ("Latvia", "LV"), ("Liechtenstein", "LI"),
    ("Lithuania", "LT"), ("Luxembourg", "LU"), ("Malta", "MT"),
    ("Moldova", "MD"), ("Monaco", "MC"), ("Montenegro", "ME"),
    ("Netherlands", "NL"), ("North Macedonia", "MK"),
    ("Norway", "NO"), ("Poland", "PL"), ("Portugal", "PT"),
    ("Romania", "RO"), ("Russia", "RU"), ("San Marino", "SM"),
    ("Serbia", "RS"), ("Slovakia", "SK"), ("Slovenia", "SI"),
    ("Spain", "ES"), ("Sweden", "SE"), ("Switzerland", "CH"),
    ("Turkey", "TR"), ("Ukraine", "UA"),
    ("United Kingdom", "GB"), ("Vatican City", "VA"),
]

EBAY_DOMAINS = {
    "AT": "www.ebay.at", "BE": "www.ebay.be", "CH": "www.ebay.ch",
    "DE": "www.ebay.de", "ES": "www.ebay.es", "FR": "www.ebay.fr",
    "IE": "www.ebay.ie", "IT": "www.ebay.it", "NL": "www.ebay.nl",
    "PL": "www.ebay.pl", "UK": "www.ebay.co.uk", "GB": "www.ebay.co.uk",
}

# Curated local candidates. Each template passes a real HTTP reachability test
# before it is exported; the query placeholder is always filled with a sample.
# A successful HTTP response confirms reachability and URL construction, not
# that every shop's internal search engine returns relevant products.
COUNTRY_SHOP_CANDIDATES = {
    "Netherlands": [
        ("Concerto", "https://www.concerto.nl/search?query={query}"),
        ("Platomania", "https://www.platomania.nl/search?search={query}"),
    ],
    "Belgium": [
        ("Music Mania Records", "https://musicmaniarecords.be/search?q={query}"),
    ],
    "Germany": [
        ("HHV Records", "https://www.hhv.de/en/records/search?q={query}"),
    ],
    "France": [
        ("Fnac France", "https://www.fnac.com/SearchResult/ResultList.aspx?Search={query}"),
        ("Bigwax", "https://bigwax.io/search?type=product&q={query}"),
    ],
    "United Kingdom": [
        ("Juno Records", "https://www.juno.co.uk/search/?q%5Ball%5D%5Ball%5D={query}"),
        ("Rough Trade", "https://www.roughtrade.com/search?q={query}"),
        ("Norman Records", "https://www.normanrecords.com/search?search={query}"),
    ],
    "Ireland": [
        ("Golden Discs", "https://goldendiscs.ie/search?q={query}"),
    ],
    "Denmark": [
        ("iMusic", "https://imusic.dk/search?query={query}"),
    ],
    "Sweden": [
        ("Bengans", "https://www.bengans.com/search?search={query}"),
    ],
    "Italy": [
        ("DVDLAND", "https://www.dvdland.it/search?controller=search&s={query}"),
        ("Disco Express", "https://disco-express.it/search?controller=search&s={query}"),
        ("Cuordivinile", "https://www.cuordivinile.it/search?controller=search&s={query}"),
        ("Fonè Records Shop", "https://foneshop.it/?s={query}"),
        # Italian webshops explicitly selling physical vinyl records (vinili).
        # Search routes are tested at generation time; HTTP 403 is retained as
        # unverified because some shops block automated requests.
        ("Ciakky70 - The Record Store", "https://www.ciakky70.com/it/search?controller=search&s={query}"),
        ("Il Discomane", "https://www.discomane.com/search?q={query}"),
        ("MOVE ON Firenze", "https://moveonfirenze.com/?s={query}"),
        ("Potente Record Store", "https://www.potenterecords.com/search?q={query}"),
        ("Lettera 22 - La Bottega del Vinile", "https://lettera22dischi.it/?s={query}"),
        ("Discoteca Laziale", "https://www.discotecalaziale.com/catalogsearch/result/?q={query}"),
        ("Massive Music Store", "https://massivemusicstore.com/search?q={query}"),
        ("HiFiRecord", "https://www.hifirecord.it/?s={query}"),
        ("Rock & Folk", "https://www.rockandfolk.com/?s={query}"),
        ("Discobolandia", "https://www.discobolandia.biz/search?controller=search&s={query}"),
    ],
    "Spain": [
        ("Fnac España", "https://www.fnac.es/SearchResult/ResultList.aspx?Search={query}"),
        ("Revólver Records", "https://www.revolverrecords.com/search?q={query}"),
    ],
    "Poland": [
        ("Side One", "https://sideone.pl/search?controller=search&s={query}"),
    ],
}


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

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
                INSERT INTO sources
                    (name, url_template, enabled)
                VALUES (?, ?, ?)
                """,
                DEFAULT_SOURCES,
            )


# ---------------------------------------------------------
# URL HELPERS
# ---------------------------------------------------------

def valid_http_url(url):
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme.lower() in ("http", "https")
            and bool(parsed.netloc)
        )
    except (ValueError, AttributeError, TypeError):
        return False


def build_search_url(
    template,
    query,
    artist,
    title,
    label,
    catalog,
):
    query = query.strip()

    values = {
        "query": quote_plus(query),
        "artist": quote_plus(artist.strip()),
        "title": quote_plus(title.strip()),
        "label": quote_plus(label.strip()),
        "catalog": quote_plus(catalog.strip()),
        # Legacy placeholders remain empty for compatibility with
        # existing source templates; these are no longer search fields.
        "album": "",
        "year": "",
        "format": "",
        "query_params": urlencode({"q": query}),
    }

    try:
        result = template.format(**values)

        if not valid_http_url(result):
            return ""

        return result

    except (KeyError, ValueError, AttributeError):
        return ""


def validate_template(template):
    test_values = {
        "{query}": "test",
        "{artist}": "artist",
        "{title}": "title",
        "{album}": "album",
        "{label}": "label",
        "{catalog}": "catalog",
        "{year}": "2020",
        "{format}": "vinyl",
        "{query_params}": "q=test",
    }

    test_url = template

    for placeholder, value in test_values.items():
        test_url = test_url.replace(placeholder, value)

    return valid_http_url(test_url)


# ---------------------------------------------------------
# SOURCE DIALOG
# ---------------------------------------------------------

class SourceDialog(QDialog):

    def __init__(self, parent=None, source=None):
        super().__init__(parent)

        self.setWindowTitle("Website / Store")
        self.setMinimumWidth(500)

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
            "Available placeholders: {query}, {artist}, "
            "{title}, {label}, {catalog}, {query_params}."
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
            self.enabled_check.setChecked(
                bool(source["enabled"])
            )

    def validate_and_accept(self):
        name = self.name_edit.text().strip()
        template = self.url_edit.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Missing name",
                "Enter a source name.",
            )
            return

        if not validate_template(template):
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


# ---------------------------------------------------------
# FAVORITE DIALOG
# ---------------------------------------------------------

class FavoriteDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Add Favorite")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_edit = QLineEdit()
        self.url_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        form.addRow("Title:", self.title_edit)
        form.addRow("URL:", self.url_edit)
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    def validate_and_accept(self):
        if not self.title_edit.text().strip():
            QMessageBox.warning(
                self, "Missing title", "Enter a title."
            )
            return

        if not valid_http_url(self.url_edit.text().strip()):
            QMessageBox.warning(
                self, "Invalid URL", "Enter a valid URL."
            )
            return

        self.accept()

    def values(self):
        return (
            self.title_edit.text().strip(),
            self.url_edit.text().strip(),
            self.notes_edit.text().strip(),
        )


class DuckDuckGoResultsParser(HTMLParser):
    """Extract organic result links from DuckDuckGo's HTML results page."""
    def __init__(self):
        super().__init__()
        self.results = []
        self._anchor = None
        self._inside_result = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._anchor = {"url": attrs.get("href", ""), "title": ""}
            self._inside_result = True

    def handle_data(self, data):
        if self._inside_result and self._anchor is not None:
            self._anchor["title"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._inside_result and self._anchor is not None:
            self._anchor["title"] = self._anchor["title"].strip()
            if self._anchor["url"] and self._anchor["title"]:
                self.results.append(self._anchor)
            self._anchor = None
            self._inside_result = False


class CountryWebsiteResultsDialog(QDialog):
    """Review discovered shops, test search URL templates, and export successes."""
    def __init__(self, country, rows, parent=None):
        super().__init__(parent)
        self.country = country
        self.setWindowTitle(f"Search Websites — {country}")
        self.resize(1120, 650)
        layout = QVBoxLayout(self)
        self.info_label = QLabel(
            "Select webshops, then click 'Test / Generate Search URL'. "
            "Only positive search tests receive a reusable URL template."
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Select", "Website", "Website URL", "Search URL template", "Test result"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.rows = []
        for row_data in rows:
            self.add_result(row_data)
        buttons = QHBoxLayout()
        self.test_button = QPushButton("Test / Generate Search URL")
        self.test_button.clicked.connect(self.test_selected_rows)
        self.export_button = QPushButton("Export Successful CSV")
        self.export_button.clicked.connect(self.export_successful_csv)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(self.test_button)
        buttons.addWidget(self.export_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def add_result(self, data):
        row = self.table.rowCount()
        self.table.insertRow(row)
        check = QCheckBox()
        check.setChecked(True)
        check.setToolTip("Select this website for search URL testing")
        self.table.setCellWidget(row, 0, check)
        self.table.setItem(row, 1, QTableWidgetItem(data["name"]))
        self.table.setItem(row, 2, QTableWidgetItem(data["url"]))
        self.table.setItem(row, 3, QTableWidgetItem("Not tested"))
        self.table.setItem(row, 4, QTableWidgetItem("Awaiting search URL test"))
        self.rows.append({**data, "template": "", "test_status": "Not tested"})

    def selected_rows(self):
        return [i for i in range(self.table.rowCount())
                if self.table.cellWidget(i, 0).isChecked()]

    def test_selected_rows(self):
        selected = self.selected_rows()
        if not selected:
            QMessageBox.information(self, "Search Websites", "Select at least one website.")
            return
        self.test_button.setEnabled(False)
        try:
            for row in selected:
                data = self.rows[row]
                self.table.item(row, 3).setText("Testing search patterns...")
                self.table.item(row, 4).setText("Testing...")
                QApplication.processEvents()
                template, status = test_search_templates(data["url"], self.country)
                data["template"] = template or ""
                data["test_status"] = status
                self.table.item(row, 3).setText(template or "No positive search pattern found")
                self.table.item(row, 3).setToolTip(template or "")
                self.table.item(row, 4).setText(status)
        finally:
            self.test_button.setEnabled(True)
        successes = sum(1 for i in selected if self.rows[i]["template"])
        QMessageBox.information(
            self, "Search URL Test Complete",
            f"Positive search tests: {successes} of {len(selected)} selected websites.\n\n"
            "A positive test means the candidate search route returned a page with product/search evidence; "
            "please open the URL in a browser before relying on it."
        )

    def export_successful_csv(self):
        rows = [r for r in self.rows if r["template"] and r["test_status"].startswith("PASS")]
        if not rows:
            QMessageBox.information(self, "Export CSV", "No positively tested search URLs are available yet.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export positively tested websites",
            f"VinylFinder_{self.country.replace(' ', '_')}_sources.csv", "CSV files (*.csv)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"
        fields = ["name", "url_template", "enabled", "country", "test_status", "website_url", "tested_at"]
        now = datetime.now().isoformat(timespec="seconds")
        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({
                        "name": row["name"], "url_template": row["template"],
                        "enabled": "1", "country": self.country,
                        "test_status": row["test_status"], "website_url": row["url"],
                        "tested_at": now,
                    })
        except OSError as exc:
            QMessageBox.warning(self, "Export CSV", f"Could not save CSV:\n{exc}")
            return
        QMessageBox.information(self, "Export CSV", f"Exported {len(rows)} tested websites to:\n{file_path}")


def test_search_templates(base_url, country):
    """Try common store search routes and require product/search evidence."""
    base = base_url.rstrip("/")
    query = "vinile" if country == "Italy" else "vinyl"
    encoded = quote_plus(query)
    candidates = [
        f"{base}/search?q={{query}}",
        f"{base}/search?query={{query}}",
        f"{base}/search?type=product&q={{query}}",
        f"{base}/search?controller=search&s={{query}}",
        f"{base}/catalogsearch/result/?q={{query}}",
        f"{base}/?s={{query}}&post_type=product",
        f"{base}/?s={{query}}",
        f"{base}/search/?q%5Ball%5D%5Ball%5D={{query}}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    for template in candidates:
        test_url = template.replace("{query}", encoded)
        try:
            request = urllib.request.Request(test_url, headers=headers)
            with urllib.request.urlopen(request, timeout=4) as response:
                status = getattr(response, "status", 200)
                final_url = response.geturl()
                body = response.read(180000).decode("utf-8", errors="ignore").lower()
            if not (200 <= status < 300) or not valid_http_url(final_url):
                continue
            # Require signals of a search/product page; generic homepage 200s don't count.
            query_evidence = encoded.lower() in final_url.lower() or query in body or encoded.replace("+", " ") in body
            product_evidence = any(term in body for term in (
                "vinile", "vinyl", "record", "dischi", "cd", "product", "prodotto", "risultati della ricerca", "search results"
            ))
            search_evidence = any(term in final_url.lower() for term in ("search", "?s=", "catalogsearch", "controller=search")) or any(
                term in body for term in ("search-form", "search-form__input", "woocommerce-product-search", "product-list", "search results", "risultati della ricerca")
            )
            if query_evidence and product_evidence and search_evidence:
                return template, f"PASS — HTTP {status}; search/product evidence found"
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                # 403 cannot prove the route is broken; do not claim a positive result.
                last_status = "HTTP 403 — browser verification required"
            else:
                last_status = f"HTTP {exc.code}"
        except Exception as exc:
            last_status = str(exc).replace("\n", " ")[:90] or exc.__class__.__name__
    return "", f"No positive test; last response: {locals().get('last_status', 'no matching search route')}"


# ---------------------------------------------------------
# MAIN WINDOW
# ---------------------------------------------------------

class VinylFinder(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(900, 600)

        self.tabs = QTabWidget()

        self.tabs.addTab(
            self.create_search_tab(), "Search Records"
        )
        self.tabs.addTab(
            self.create_sources_tab(), "Manage Sources"
        )
        self.tabs.addTab(
            self.create_favorites_tab(), "Favorites"
        )
        self.tabs.addTab(
            self.create_history_tab(), "Search History"
        )

        self.setCentralWidget(self.tabs)

        self.refresh_sources()
        self.refresh_favorites()
        self.refresh_history()

        self.statusBar().showMessage(
            f"Database: {DB_PATH}"
        )

    # -----------------------------------------------------
    # COMMON TABLE CONFIGURATION
    # -----------------------------------------------------

    @staticmethod
    def configure_table(table):
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setAlternatingRowColors(True)
        # Black background with white text for consistent contrast.
        table.setStyleSheet("""
            QTableWidget {
                background-color: #000000;
                alternate-background-color: #181818;
                color: #ffffff;
                gridline-color: #555555;
                selection-background-color: #3d5f86;
                selection-color: #ffffff;
            }
            QTableWidget::item {
                background-color: #000000;
                color: #ffffff;
                padding: 4px;
            }
            QTableWidget::item:alternate {
                background-color: #181818;
                color: #ffffff;
            }
            QTableWidget::item:selected {
                background-color: #3d5f86;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #292929;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #555555;
                font-weight: bold;
            }
        """)

        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )

    # -----------------------------------------------------
    # SEARCH TAB
    # -----------------------------------------------------

    def create_search_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()

        self.artist_edit = QLineEdit()
        self.title_edit = QLineEdit()
        self.label_edit = QLineEdit()
        self.catalog_edit = QLineEdit()

        form.addRow("Artist:", self.artist_edit)
        form.addRow("Title:", self.title_edit)
        form.addRow("Record label:", self.label_edit)
        form.addRow("Catalog number:", self.catalog_edit)

        layout.addLayout(form)

        buttons = QHBoxLayout()

        search_btn = QPushButton("Search Enabled Sources")
        search_btn.clicked.connect(self.search_sources)

        clear_btn = QPushButton("Clear Filters")
        clear_btn.clicked.connect(self.clear_filters)

        buttons.addWidget(search_btn)
        buttons.addWidget(clear_btn)

        layout.addLayout(buttons)

        self.results_table = QTableWidget(0, 3)

        self.results_table.setHorizontalHeaderLabels([
            "Website / Store",
            "Search URL",
            "Action",
        ])

        self.configure_table(self.results_table)

        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(2, 155)
        self.results_table.verticalHeader().setDefaultSectionSize(42)

        layout.addWidget(self.results_table, 1)

        return page

    def current_query_parts(self):
        artist = self.artist_edit.text().strip()
        title = self.title_edit.text().strip()
        label = self.label_edit.text().strip()
        catalog = self.catalog_edit.text().strip()

        search_terms = [
            artist,
            title,
            label,
            catalog,
        ]

        search_terms = [
            term for term in search_terms if term
        ]

        return {
            "artist": artist,
            "title": title,
            "label": label,
            "catalog": catalog,
            "query": " ".join(search_terms),
        }

    def enabled_sources(self):
        with connect_db() as conn:
            return conn.execute(
                """
                SELECT *
                FROM sources
                WHERE enabled = 1
                ORDER BY name
                """
            ).fetchall()

    def record_search(self, query):
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO searches (query, created_at)
                VALUES (?, ?)
                """,
                (
                    query,
                    datetime.now().isoformat(
                        timespec="seconds"
                    ),
                ),
            )

        self.refresh_history()

    def search_sources(self):
        parts = self.current_query_parts()

        # De prijs- en conditiefilters worden niet automatisch
        # door iedere website ondersteund. Ze blijven onderdeel
        # van de algemene zoektekst, waar van toepassing.
        query = parts["query"]

        if not query:
            QMessageBox.information(
                self,
                "Search",
                "Enter at least one search criterion.",
            )
            return

        sources = self.enabled_sources()

        if not sources:
            QMessageBox.information(
                self,
                "Search",
                "No enabled sources are configured.\n\n"
                "Open Manage Sources and enable a website.",
            )
            return

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
            self.results_table.setRowCount(0)

            parts_for_url = dict(parts)

            # Geef winkels ook de ingevulde aanvullende
            # criteria mee in de algemene query.
            parts_for_url["query"] = query

            for source in sources:
                url = build_search_url(
                    source["url_template"],
                    parts_for_url["query"],
                    parts_for_url["artist"],
                    parts_for_url["title"],
                    parts_for_url["label"],
                    parts_for_url["catalog"],
                )

                if not valid_http_url(url):
                    continue

                row = self.results_table.rowCount()
                self.results_table.insertRow(row)

                self.results_table.setItem(
                    row,
                    0,
                    QTableWidgetItem(source["name"]),
                )

                url_item = QTableWidgetItem(url)
                url_item.setToolTip(url)

                self.results_table.setItem(
                    row, 1, url_item
                )

                open_button = QPushButton("Open Search")
                open_button.setMinimumSize(130, 30)
                open_button.setToolTip("Open this search in your web browser")
                open_button.clicked.connect(
                    lambda checked=False, target=url:
                        webbrowser.open(target)
                )
                self.results_table.setRowHeight(row, 42)
                self.results_table.setCellWidget(
                    row, 2, open_button
                )

            self.record_search(query)

            count = self.results_table.rowCount()

            self.statusBar().showMessage(
                f"Prepared {count} search destinations."
            )

            if count == 0:
                QMessageBox.information(
                    self,
                    "Search",
                    "No valid search destinations were prepared.\n\n"
                    "Check the URL templates in Manage Sources.",
                )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Search Error",
                f"Could not prepare the searches:\n{exc}",
            )

        finally:
            progress.close()
            progress.deleteLater()

    # -----------------------------------------------------
    # CLEAR FILTERS
    # -----------------------------------------------------

    def clear_filters(self):
        for widget in (
            self.artist_edit,
            self.title_edit,
            self.label_edit,
            self.catalog_edit,
        ):
            widget.clear()

        self.results_table.setRowCount(0)

        self.statusBar().showMessage("Filters cleared.")

    # -----------------------------------------------------
    # MANAGE SOURCES TAB
    # -----------------------------------------------------

    def create_sources_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.sources_table = QTableWidget(0, 4)

        self.sources_table.setHorizontalHeaderLabels([
            "Select",
            "Name",
            "Search URL Template",
            "Enabled",
        ])

        self.configure_table(self.sources_table)
        # Klik op Yes/No in een regel om de bron direct in/uit te schakelen.
        self.sources_table.cellClicked.connect(self.toggle_source_at_row)

        header = self.sources_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.sources_table)

        country_row = QHBoxLayout()
        country_row.addWidget(QLabel("Generate webshop list for country:"))
        self.country_picklist = QComboBox()
        for country_name, country_code in EUROPEAN_COUNTRIES:
            self.country_picklist.addItem(country_name, country_code)
        self.country_picklist.setCurrentText("Netherlands")
        country_row.addWidget(self.country_picklist, 1)
        search_websites_btn = QPushButton("Search Websites")
        search_websites_btn.clicked.connect(self.search_websites_online)
        country_row.addWidget(search_websites_btn)
        generate_country_btn = QPushButton("Generate Country CSV")
        generate_country_btn.clicked.connect(self.generate_country_sources_csv)
        country_row.addWidget(generate_country_btn)
        layout.addLayout(country_row)

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

        item = self.sources_table.item(row, 1)

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

            # Elke bron krijgt een selectievakje; meerdere bronnen
            # kunnen tegelijk worden geselecteerd voor Enable / Disable.
            check_item = QTableWidgetItem("")
            check_item.setFlags(
                (check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                & ~Qt.ItemFlag.ItemIsEditable
            )
            check_item.setCheckState(Qt.CheckState.Unchecked)
            self.sources_table.setItem(row, 0, check_item)

            name_item = QTableWidgetItem(source["name"])
            name_item.setData(
                Qt.ItemDataRole.UserRole,
                source["id"],
            )
            self.sources_table.setItem(row, 1, name_item)

            self.sources_table.setItem(
                row,
                2,
                QTableWidgetItem(source["url_template"]),
            )

            self.sources_table.setItem(
                row,
                3,
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
                    """
                    INSERT INTO sources
                        (name, url_template, enabled)
                    VALUES (?, ?, ?)
                    """,
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
                self,
                "Edit Source",
                "Select a source first.",
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
                """
                UPDATE sources
                SET name = ?, url_template = ?, enabled = ?
                WHERE id = ?
                """,
                (name, url, enabled, source_id),
            )

        self.refresh_sources()

    def toggle_source_at_row(self, row, column):
        # Alleen klikken op de Enabled-kolom (Yes/No) wisselt de status.
        if column != 3:
            return

        name_item = self.sources_table.item(row, 1)
        if not name_item:
            return

        source_id = name_item.data(Qt.ItemDataRole.UserRole)
        if source_id is None:
            return

        with connect_db() as conn:
            conn.execute(
                """
                UPDATE sources
                SET enabled = 1 - enabled
                WHERE id = ?
                """,
                (source_id,),
            )

        self.refresh_sources()

    def toggle_source(self):
        # Draai de status om van alle aangevinkte bronnen.
        selected_ids = []
        for row in range(self.sources_table.rowCount()):
            check_item = self.sources_table.item(row, 0)
            name_item = self.sources_table.item(row, 1)
            if (
                check_item
                and check_item.checkState() == Qt.CheckState.Checked
                and name_item
            ):
                source_id = name_item.data(Qt.ItemDataRole.UserRole)
                if source_id is not None:
                    selected_ids.append(source_id)

        if not selected_ids:
            QMessageBox.information(
                self,
                "Sources",
                "Tick the checkbox next to at least one website first.",
            )
            return

        with connect_db() as conn:
            conn.executemany(
                """
                UPDATE sources
                SET enabled = 1 - enabled
                WHERE id = ?
                """,
                [(source_id,) for source_id in selected_ids],
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

    def search_websites_online(self):
        country = self.country_picklist.currentText()
        country_code = self.country_picklist.currentData()
        country_queries = {
            "Italy": 'negozio online vinili CD compra dischi vinile',
            "Netherlands": 'online platenwinkel vinyl platen cd webshop',
            "Germany": 'Online Schallplatten Shop Vinyl CDs',
            "France": 'boutique en ligne disques vinyles CD',
            "Spain": 'tienda online discos vinilo CD',
            "United Kingdom": 'online record shop vinyl records CDs',
        }
        query = country_queries.get(
            country, f'online record shop vinyl records CDs {country}'
        )
        candidates = []
        errors = []
        search_queries = [
            query,
            f'"vinili" "acquista online" {country}',
            f'negozio dischi vinile CD shop online {country}',
        ]
        for search_term in search_queries:
            search_url = "https://html.duckduckgo.com/html/?q=" + quote_plus(search_term)
            request = urllib.request.Request(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=12) as response:
                    html = response.read(1500000).decode("utf-8", errors="ignore")
                parser = DuckDuckGoResultsParser()
                parser.feed(html)
                for result in parser.results:
                    url = result["url"]
                    title = result["title"]
                    if "duckduckgo.com/l/" in url:
                        redirect_values = parse_qs(urlparse(url).query).get("uddg", [])
                        if redirect_values:
                            url = unquote(redirect_values[0])
                    if not valid_http_url(url):
                        continue
                    host = urlparse(url).netloc.lower()
                    if any(domain in host for domain in (
                        "duckduckgo.com", "google.com", "bing.com", "youtube.com", "spotify.com",
                        "soundcloud.com", "deezer.com", "tidal.com", "music.apple.com", "amazon.com/gp/video"
                    )):
                        continue
                    combined = title.lower() + " " + url.lower()
                    if any(term in combined for term in (
                        "streaming", "streaming music", "listen online", "mp3 download", "digital music only"
                    )):
                        continue
                    # Search results are candidates, not assumed to be valid shops.
                    candidates.append({"name": title[:100], "url": url})
            except Exception as exc:
                errors.append(f"Search '{search_term}': {str(exc)[:120]}")

        # Merge curated country-specific shops so search-engine markup or throttling
        # cannot erase known physical-record retailers from the review list.
        for name, template in COUNTRY_SHOP_CANDIDATES.get(country, []):
            parsed_template = urlparse(template)
            base = f"{parsed_template.scheme}://{parsed_template.netloc}"
            if not valid_http_url(base):
                continue
            candidates.append({"name": name, "url": base})

        # Include the source platforms as candidates, but never label them as
        # positively tested until the user explicitly tests their search routes.
        ebay_domain = EBAY_DOMAINS.get(country_code, "www.ebay.com")
        candidates.extend([
            {"name": "Discogs", "url": "https://www.discogs.com"},
            {"name": "eBay", "url": f"https://{ebay_domain}"},
        ])
        unique = []
        seen = set()
        for candidate in candidates:
            parsed = urlparse(candidate["url"])
            base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
            key = base.casefold()
            if not base or key in seen:
                continue
            seen.add(key)
            candidate["url"] = base
            unique.append(candidate)

        if not unique:
            message = "No website candidates were found."
            if errors:
                message += "\n\n" + "\n".join(errors)
            QMessageBox.warning(self, "Search Websites", message)
            return

        if errors:
            QMessageBox.information(
                self,
                "Search Websites",
                "Some internet searches could not be completed. Known country-specific candidates "
                "are still included where available.\n\n" + "\n".join(errors[:3]),
            )
        dialog = CountryWebsiteResultsDialog(country, unique, self)
        dialog.exec()

    def generate_country_sources_csv(self):
        country = self.country_picklist.currentText()
        country_code = self.country_picklist.currentData()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save tested webshop list for {country}",
            f"VinylFinder_{country.replace(' ', '_')}_sources.csv",
            "CSV files (*.csv)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        ebay_domain = EBAY_DOMAINS.get(country_code, "www.ebay.com")
        candidates = [
            ("Discogs", "https://www.discogs.com/search/?q={query}&type=all"),
            ("eBay", f"https://{ebay_domain}/sch/i.html?_nkw={{query}}"),
            ("Bandcamp", "https://bandcamp.com/search?q={query}"),
        ]
        candidates.extend(COUNTRY_SHOP_CANDIDATES.get(country, []))

        # Avoid duplicate names and duplicate templates in the output.
        unique_candidates = []
        seen = set()
        for name, template in candidates:
            key = (name.casefold(), template.casefold())
            if key not in seen:
                seen.add(key)
                unique_candidates.append((name, template))

        # Use a country-language term relevant to physical records rather than
        # the generic English phrase "vinyl test". This also helps validate
        # the site's actual product-search route with a meaningful query.
        test_query = "vinile" if country == "Italy" else "vinyl"
        passed_rows = []
        unverified = []
        failed = []
        tested_at = datetime.now().isoformat(timespec="seconds")

        progress = QProgressDialog(
            "Testing website search URLs...",
            "Cancel",
            0,
            len(unique_candidates),
            self,
        )
        progress.setWindowTitle("Generate Country CSV")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        cancelled = False
        try:
            for candidate_index, (name, template) in enumerate(unique_candidates, start=1):
                progress.setLabelText(f"Testing {name} ({candidate_index}/{len(unique_candidates)})...")
                progress.setValue(candidate_index - 1)
                QApplication.processEvents()
                if progress.wasCanceled():
                    cancelled = True
                    break
                if "{query}" not in template or not validate_template(template):
                    failed.append((name, "invalid search template"))
                    continue

                test_url = template.replace("{query}", quote_plus(test_query))
                request = urllib.request.Request(
                    test_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "AppleWebKit/537.36 Chrome/130 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    },
                    method="GET",
                )
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        status = getattr(response, "status", 200)
                        final_url = response.geturl()
                        # Read a small part to ensure the response actually begins.
                        response.read(1024)
                    if 200 <= status < 400 and valid_http_url(final_url):
                        passed_rows.append({
                            "name": name,
                            "url_template": template,
                            "enabled": "1",
                            "country": country,
                            "test_query": test_query,
                            "test_status": f"HTTP {status} OK",
                            "test_url": test_url,
                            "tested_at": tested_at,
                        })
                    else:
                        failed.append((name, f"HTTP {status}"))
                except urllib.error.HTTPError as exc:
                    # Some large platforms block scripted requests with HTTP 403.
                    # This is not proof that the search URL is broken in a normal
                    # browser, so keep it in the CSV but clearly mark it unverified.
                    if exc.code == 403:
                        passed_rows.append({
                            "name": name,
                            "url_template": template,
                            "enabled": "1",
                            "country": country,
                            "test_query": test_query,
                            "test_status": "HTTP 403 - automated request blocked; verify in browser",
                            "test_url": test_url,
                            "tested_at": tested_at,
                        })
                        unverified.append((name, "HTTP 403: automated test blocked; exported for browser verification"))
                    else:
                        failed.append((name, f"HTTP {exc.code}: {exc.reason}"))
                except Exception as exc:
                    reason = str(exc).replace("\n", " ")[:100]
                    failed.append((name, reason or exc.__class__.__name__))
        finally:
            progress.close()
            progress.deleteLater()

        fieldnames = [
            "name", "url_template", "enabled", "country",
            "test_query", "test_status", "test_url", "tested_at",
        ]
        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(passed_rows)
        except OSError as exc:
            QMessageBox.warning(
                self, "Country CSV", f"Could not save the CSV file:\n{exc}"
            )
            return

        verified_count = sum(
            1 for row in passed_rows
            if row["test_status"].startswith("HTTP ")
            and "automated request blocked" not in row["test_status"]
        )
        message = (
            f"Country: {country}\n"
            f"Search URLs verified by live HTTP response: {verified_count}\n"
            f"URLs exported but requiring browser verification: {len(unverified)}\n"
            f"Candidates not exported (failed test): {len(failed)}\n"
            + ("Testing was cancelled by the user.\n" if cancelled else "")
            + "\n"
            f"Saved CSV: {file_path}\n\n"
            "The CSV contains the columns required by Import CSV (name, url_template, enabled) "
            "plus test details. HTTP 403 entries are included but marked as unverified because "
            "some websites block automated tests. Open those search URLs in a normal browser "
            "before relying on them. Import CSV ignores the extra test columns."
        )
        if unverified:
            message += "\n\nExported but not verified in browser:\n" + "\n".join(
                f"• {name}: {reason}" for name, reason in unverified[:12]
            )
            if len(unverified) > 12:
                message += f"\n…and {len(unverified) - 12} more."
        if failed:
            message += "\n\nNot exported (failed test):\n" + "\n".join(
                f"• {name}: {reason}" for name, reason in failed[:12]
            )
            if len(failed) > 12:
                message += f"\n…and {len(failed) - 12} more."
        QMessageBox.information(self, "Country CSV Generated", message)

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
                        sample,
                        delimiters=",;\t",
                    )
                except csv.Error:
                    dialect = csv.excel

                reader = csv.DictReader(
                    csv_file,
                    dialect=dialect,
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

                required = {"name", "url_template"}

                if not required.issubset(
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

                        if not validate_template(template):
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
                            """
                            SELECT 1 FROM sources
                            WHERE lower(name) = lower(?)
                            """,
                            (name,),
                        ).fetchone()

                        if exists:
                            skipped += 1
                            continue

                        conn.execute(
                            """
                            INSERT INTO sources
                                (name, url_template, enabled)
                            VALUES (?, ?, ?)
                            """,
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

    # -----------------------------------------------------
    # FAVORITES TAB
    # -----------------------------------------------------

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

        add_btn = QPushButton("Add Favorite")
        add_btn.clicked.connect(self.add_favorite)

        open_btn = QPushButton("Open Selected URL")
        open_btn.clicked.connect(self.open_selected_favorite)

        delete_btn = QPushButton("Remove Favorite")
        delete_btn.clicked.connect(self.delete_favorite)

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
                """
                SELECT * FROM favorites
                ORDER BY created_at DESC
                """
            ).fetchall()

        self.favorites_table.setRowCount(0)

        for fav in rows:
            row = self.favorites_table.rowCount()
            self.favorites_table.insertRow(row)

            title = QTableWidgetItem(fav["title"])
            title.setData(
                Qt.ItemDataRole.UserRole,
                fav["id"],
            )

            self.favorites_table.setItem(row, 0, title)

            self.favorites_table.setItem(
                row, 1, QTableWidgetItem(fav["url"])
            )

            self.favorites_table.setItem(
                row, 2,
                QTableWidgetItem(fav["notes"] or ""),
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

    def add_favorite(self):
        dialog = FavoriteDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        title, url, notes = dialog.values()

        try:
            with connect_db() as conn:
                conn.execute(
                    """
                    INSERT INTO favorites
                        (title, url, notes, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        title,
                        url,
                        notes,
                        datetime.now().isoformat(
                            timespec="seconds"
                        ),
                    ),
                )

        except sqlite3.IntegrityError:
            QMessageBox.information(
                self,
                "Favorites",
                "This URL is already a favorite.",
            )
            return

        self.refresh_favorites()

    def open_selected_favorite(self):
        row = self.favorites_table.currentRow()

        if row < 0:
            QMessageBox.information(
                self,
                "Favorites",
                "Select a favorite first.",
            )
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

        answer = QMessageBox.question(
            self,
            "Remove Favorite",
            "Remove the selected favorite?",
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        with connect_db() as conn:
            conn.execute(
                "DELETE FROM favorites WHERE id = ?",
                (fav_id,),
            )

        self.refresh_favorites()

    # -----------------------------------------------------
    # SEARCH HISTORY TAB
    # -----------------------------------------------------

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
        clear_btn.setMinimumHeight(32)
        clear_btn.setToolTip("Delete all saved searches from Search History")
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
                """
                SELECT * FROM searches
                ORDER BY id DESC
                LIMIT 500
                """
            ).fetchall()

        self.history_table.setRowCount(0)

        for item in rows:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            query_item = QTableWidgetItem(item["query"])
            query_item.setData(
                Qt.ItemDataRole.UserRole,
                item["id"],
            )

            self.history_table.setItem(row, 0, query_item)

            self.history_table.setItem(
                row,
                1,
                QTableWidgetItem(item["created_at"]),
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


# ---------------------------------------------------------
# APPLICATION ENTRY POINT
# ---------------------------------------------------------

def main():
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    # Application-wide dark theme: black backgrounds and white text.
    # Explicit colors prevent Windows 11 theme settings from reducing contrast.
    app.setStyleSheet("""
        QWidget {
            background-color: #000000;
            color: #ffffff;
        }
        QMainWindow, QDialog, QTabWidget::pane, QScrollArea {
            background-color: #000000;
            color: #ffffff;
        }
        QLabel {
            background-color: transparent;
            color: #ffffff;
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
        QSpinBox, QDoubleSpinBox {
            background-color: #111111;
            color: #ffffff;
            selection-background-color: #3d5f86;
            selection-color: #ffffff;
            border: 1px solid #666666;
            padding: 4px;
        }
        QComboBox QAbstractItemView {
            background-color: #111111;
            color: #ffffff;
            selection-background-color: #3d5f86;
            selection-color: #ffffff;
        }
        QPushButton {
            background-color: #292929;
            color: #ffffff;
            border: 1px solid #666666;
            border-radius: 3px;
            padding: 6px 10px;
        }
        QPushButton:hover {
            background-color: #3b3b3b;
        }
        QPushButton:pressed {
            background-color: #3d5f86;
        }
        QPushButton:disabled {
            background-color: #181818;
            color: #888888;
            border-color: #444444;
        }
        QTabBar::tab {
            background-color: #202020;
            color: #ffffff;
            padding: 8px 12px;
            border: 1px solid #555555;
        }
        QTabBar::tab:selected {
            background-color: #3d5f86;
            color: #ffffff;
        }
        QHeaderView::section {
            background-color: #292929;
            color: #ffffff;
            border: 1px solid #555555;
            padding: 5px;
        }
        QStatusBar {
            background-color: #111111;
            color: #ffffff;
        }
        QMenu, QMenuBar {
            background-color: #111111;
            color: #ffffff;
            border: 1px solid #555555;
        }
        QMenu::item:selected {
            background-color: #3d5f86;
            color: #ffffff;
        }
        QCheckBox {
            background-color: transparent;
            color: #ffffff;
        }
        QProgressDialog {
            background-color: #000000;
            color: #ffffff;
        }
        QMessageBox {
            background-color: #000000;
            color: #ffffff;
        }
    """)

    window = VinylFinder()
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
