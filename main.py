
import sys
import sqlite3
import csv
import re
import webbrowser
import urllib.request
import urllib.error
import threading
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
from urllib.parse import (
    quote_plus, urlencode, urlparse, parse_qs, unquote
)

from PySide6.QtCore import Qt, QObject, Signal, QThread
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QMessageBox, QDialog, QDialogButtonBox, QCheckBox,
    QLabel, QHeaderView, QAbstractItemView, QFileDialog,
    QProgressDialog, QProgressBar
)


APP_NAME = "VinylFinder"
APP_VERSION = "0.7.0"

DATA_DIR = Path.home() / "AppData" / "Local" / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "vinylfinder.db"

DEFAULT_SOURCES = [
    ("Discogs", "https://www.discogs.com/search/?{query_params}", 1),
    ("eBay", "https://www.ebay.com/sch/i.html?_nkw={query}", 1),
    ("Bandcamp", "https://bandcamp.com/search?q={query}", 1),
]

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
    "AT": "www.ebay.at", "BE": "www.ebay.be",
    "CH": "www.ebay.ch", "DE": "www.ebay.de",
    "ES": "www.ebay.es", "FR": "www.ebay.fr",
    "IE": "www.ebay.ie", "IT": "www.ebay.it",
    "NL": "www.ebay.nl", "PL": "www.ebay.pl",
    "UK": "www.ebay.co.uk", "GB": "www.ebay.co.uk",
}

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


# =========================================================
# DATABASE
# =========================================================

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
            conn.executemany("""
                INSERT INTO sources (name, url_template, enabled)
                VALUES (?, ?, ?)
            """, DEFAULT_SOURCES)


# =========================================================
# URL HELPERS
# =========================================================

def valid_http_url(url):
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme.lower() in ("http", "https")
            and bool(parsed.netloc)
        )
    except (ValueError, AttributeError, TypeError):
        return False


def build_search_url(template, query, artist="", title="", label="", catalog=""):
    query = query.strip()
    values = {
        "query": quote_plus(query),
        "artist": quote_plus(artist.strip()),
        "title": quote_plus(title.strip()),
        "label": quote_plus(label.strip()),
        "catalog": quote_plus(catalog.strip()),
        "album": "",
        "year": "",
        "format": "",
        "query_params": urlencode({"q": query}),
    }
    try:
        result = template.format(**values)
        return result if valid_http_url(result) else ""
    except (KeyError, ValueError, AttributeError):
        return ""


def validate_template(template):
    replacements = {
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
    for placeholder, value in replacements.items():
        test_url = test_url.replace(placeholder, value)
    return valid_http_url(test_url)


# =========================================================
# SEARCH RESULT DETECTION
# =========================================================

class SearchPageParser(HTMLParser):
    """Collect page text and links for conservative result detection."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text_parts = []
        self.links = []
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self._anchor = {
                "href": attrs.get("href", ""),
                "text": "",
                "class": attrs.get("class", ""),
            }

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.text_parts.append(text)
            if self._anchor is not None:
                self._anchor["text"] += " " + text

    def handle_endtag(self, tag):
        if tag == "a" and self._anchor is not None:
            self.links.append(self._anchor)
            self._anchor = None


def check_search_result(url, query):
    """
    Controleer een gegenereerde zoek-URL.

    Positief:
      - HTTP-response is succesvol;
      - pagina bevat zoek- of productstructuur;
      - er is aanvullend bewijs van resultaten.

    HTTP 200 alleen is nadrukkelijk niet voldoende.
    Een geblokkeerde of onduidelijke pagina blijft onbevestigd.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/130 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }

    if not valid_http_url(url):
        return False, "ONBEVESTIGD — ongeldige URL"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            status = getattr(response, "status", 200)
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "").lower()

            if not (200 <= status < 300):
                return False, f"ONBEVESTIGD — HTTP {status}"

            if "html" not in content_type:
                return False, "ONBEVESTIGD — geen HTML-resultatenpagina"

            body = response.read(700000).decode(
                "utf-8", errors="ignore"
            )

        parser = SearchPageParser()
        parser.feed(body)

        text = " ".join(parser.text_parts).lower()
        html = body.lower()
        final_url_lower = final_url.lower()

        blocked_terms = (
            "captcha", "verify you are human", "access denied",
            "robot check", "temporarily blocked",
            "unusual traffic", "enable javascript to continue",
        )
        if any(term in text or term in html for term in blocked_terms):
            return False, "ONBEVESTIGD — website blokkeert controle"

        search_structure = any(term in (
            final_url_lower + " " + html[:150000]
        ) for term in (
            "search", "catalogsearch", "search-results",
            "search_result", "woocommerce-product-search",
            "product-list", "product-listing", "result__a",
            "s=",
        ))

        product_terms = (
            "vinyl", "vinile", "record", "records", "product",
            "products", "dischi", "platen", "album",
            "search results", "risultati della ricerca",
            "no results", "no products found",
        )
        product_evidence = any(term in text for term in product_terms)

        query_terms = [
            part.lower()
            for part in re.split(r"\s+", query.strip())
            if len(part) >= 3
        ]
        query_evidence = (
            not query_terms
            or any(term in text for term in query_terms)
            or any(term in final_url_lower for term in query_terms)
        )

        # Zoek naar zichtbare productlinks.
        product_link_count = 0
        for link in parser.links:
            combined = (
                link.get("href", "") + " "
                + link.get("text", "") + " "
                + link.get("class", "")
            ).lower()
            if any(term in combined for term in (
                "product", "listing", "release", "item",
                "vinyl", "record", "album",
            )):
                product_link_count += 1

        has_result_structure = (
            search_structure
            and (
                product_link_count > 0
                or (
                    product_evidence
                    and query_evidence
                    and len(parser.text_parts) >= 10
                )
            )
        )

        if has_result_structure:
            return True, f"PASS — HTTP {status}; zoekresultaten bevestigd"

        return False, "ONBEVESTIGD — geen overtuigend resultaatbewijs"

    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return False, "ONBEVESTIGD — HTTP 403, browsercontrole nodig"
        return False, f"ONBEVESTIGD — HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, f"ONBEVESTIGD — netwerkfout: {str(exc.reason)[:70]}"
    except Exception as exc:
        return False, (
            "ONBEVESTIGD — "
            + str(exc).replace("\n", " ")[:70]
        )


class SearchWorker(QObject):
    """Voert websitecontroles uit buiten de GUI-thread."""

    result_ready = Signal(int, bool, str)
    finished = Signal()

    def __init__(self, jobs):
        super().__init__()
        self.jobs = jobs

    def run(self):
        try:
            for row, url, query in self.jobs:
                positive, status = check_search_result(url, query)
                self.result_ready.emit(row, positive, status)
        finally:
            self.finished.emit()


# =========================================================
# SOURCE DIALOG
# =========================================================

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
            "Placeholders: {query}, {artist}, {title}, {label}, "
            "{catalog}, {query_params}."
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
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Missing name", "Enter a source name.")
            return
        if not validate_template(self.url_edit.text().strip()):
            QMessageBox.warning(
                self, "Invalid URL",
                "Enter a valid HTTP or HTTPS URL template."
            )
            return
        self.accept()

    def values(self):
        return (
            self.name_edit.text().strip(),
            self.url_edit.text().strip(),
            int(self.enabled_check.isChecked()),
        )


# =========================================================
# FAVORITE DIALOG
# =========================================================

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
            QMessageBox.warning(self, "Missing title", "Enter a title.")
            return
        if not valid_http_url(self.url_edit.text().strip()):
            QMessageBox.warning(self, "Invalid URL", "Enter a valid URL.")
            return
        self.accept()

    def values(self):
        return (
            self.title_edit.text().strip(),
            self.url_edit.text().strip(),
            self.notes_edit.text().strip(),
        )


# =========================================================
# WEBSITE SEARCH RESULT PARSER
# =========================================================

class DuckDuckGoResultsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "result__a" in attrs.get("class", ""):
            self._anchor = {
                "url": attrs.get("href", ""),
                "title": "",
            }

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor["title"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._anchor is not None:
            self._anchor["title"] = self._anchor["title"].strip()
            if self._anchor["url"] and self._anchor["title"]:
                self.results.append(self._anchor)
            self._anchor = None


# =========================================================
# COUNTRY WEBSITE RESULTS DIALOG
# =========================================================

class CountryWebsiteResultsDialog(QDialog):
    def __init__(self, country, rows, parent=None):
        super().__init__(parent)
        self.country = country
        self.rows = []

        self.setWindowTitle(f"Search Websites — {country}")
        self.resize(1120, 650)
        layout = QVBoxLayout(self)

        self.info_label = QLabel(
            "Select websites and test their search templates. "
            "Only positively tested templates are exported."
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Select", "Website", "Website URL",
            "Search URL template", "Test result"
        ])
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setAlternatingRowColors(True)

        for col in (0, 1):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        for col in (2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Stretch
            )

        layout.addWidget(self.table, 1)

        for data in rows:
            self.add_result(data)

        buttons = QHBoxLayout()
        test_button = QPushButton("Test / Generate Search URL")
        test_button.clicked.connect(self.test_selected_rows)
        export_button = QPushButton("Export Successful CSV")
        export_button.clicked.connect(self.export_successful_csv)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        buttons.addWidget(test_button)
        buttons.addWidget(export_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.test_button = test_button

    def add_result(self, data):
        row = self.table.rowCount()
        self.table.insertRow(row)

        check = QCheckBox()
        check.setChecked(True)
        self.table.setCellWidget(row, 0, check)
        self.table.setItem(row, 1, QTableWidgetItem(data["name"]))
        self.table.setItem(row, 2, QTableWidgetItem(data["url"]))
        self.table.setItem(row, 3, QTableWidgetItem("Not tested"))
        self.table.setItem(row, 4, QTableWidgetItem("Awaiting test"))

        self.rows.append({
            **data,
            "template": "",
            "test_status": "Not tested",
        })

    def selected_rows(self):
        return [
            i for i in range(self.table.rowCount())
            if self.table.cellWidget(i, 0).isChecked()
        ]

    def test_selected_rows(self):
        selected = self.selected_rows()
        if not selected:
            QMessageBox.information(
                self, "Search Websites", "Select at least one website."
            )
            return

        self.test_button.setEnabled(False)
        try:
            for row in selected:
                data = self.rows[row]
                self.table.item(row, 3).setText("Testing...")
                self.table.item(row, 4).setText("Checking search results...")
                QApplication.processEvents()

                template, status = test_search_templates(
                    data["url"], self.country
                )
                data["template"] = template or ""
                data["test_status"] = status

                self.table.item(row, 3).setText(
                    template or "No positive search template"
                )
                self.table.item(row, 3).setToolTip(template or "")
                self.table.item(row, 4).setText(status)
        finally:
            self.test_button.setEnabled(True)

        successes = sum(
            1 for i in selected if self.rows[i]["template"]
        )
        QMessageBox.information(
            self, "Search URL Test Complete",
            f"Positive search tests: {successes} of {len(selected)}.\n\n"
            "A positive test is evidence, not a guarantee that every "
            "future search will return products."
        )

    def export_successful_csv(self):
        rows = [
            r for r in self.rows
            if r["template"] and r["test_status"].startswith("PASS")
        ]
        if not rows:
            QMessageBox.information(
                self, "Export CSV",
                "No positively tested search URLs are available."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export positively tested websites",
            f"VinylFinder_{self.country.replace(' ', '_')}_sources.csv",
            "CSV files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        fields = [
            "name", "url_template", "enabled", "country",
            "test_status", "website_url", "tested_at"
        ]
        now = datetime.now().isoformat(timespec="seconds")

        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({
                        "name": row["name"],
                        "url_template": row["template"],
                        "enabled": "1",
                        "country": self.country,
                        "test_status": row["test_status"],
                        "website_url": row["url"],
                        "tested_at": now,
                    })
        except OSError as exc:
            QMessageBox.warning(self, "Export CSV", str(exc))
            return

        QMessageBox.information(
            self, "Export CSV",
            f"Exported {len(rows)} websites to:\n{path}"
        )


def test_search_templates(base_url, country):
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

    for template in candidates:
        test_url = template.replace("{query}", encoded)
        positive, status = check_search_result(test_url, query)
        if positive:
            return template, status

    return "", "No positive test; search route not confirmed"


# =========================================================
# MAIN WINDOW
# =========================================================

class VinylFinder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(1000, 650)

        self.search_thread = None
        self.search_worker = None
        self.search_jobs = []
        self.search_progress = None

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

    @staticmethod
    def configure_table(table):
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.setAlternatingRowColors(True)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #000000;
                alternate-background-color: #181818;
                color: #ffffff; gridline-color: #555555;
                selection-background-color: #3d5f86;
                selection-color: #ffffff;
            }
            QTableWidget::item {
                background-color: #000000;
                color: #ffffff; padding: 4px;
            }
            QTableWidget::item:alternate {
                background-color: #181818; color: #ffffff;
            }
            QTableWidget::item:selected {
                background-color: #3d5f86; color: #ffffff;
            }
            QHeaderView::section {
                background-color: #292929; color: #ffffff;
                padding: 5px; border: 1px solid #555555;
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
            "Website / Store", "Search URL", "Action"
        ])
        self.configure_table(self.results_table)

        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(2, 220)
        self.results_table.verticalHeader().setDefaultSectionSize(42)
        layout.addWidget(self.results_table, 1)
        return page

    def current_query_parts(self):
        artist = self.artist_edit.text().strip()
        title = self.title_edit.text().strip()
        label = self.label_edit.text().strip()
        catalog = self.catalog_edit.text().strip()
        terms = [x for x in (artist, title, label, catalog) if x]
        return {
            "artist": artist,
            "title": title,
            "label": label,
            "catalog": catalog,
            "query": " ".join(terms),
        }

    def enabled_sources(self):
        with connect_db() as conn:
            return conn.execute("""
                SELECT * FROM sources
                WHERE enabled = 1 ORDER BY name
            """).fetchall()

    def record_search(self, query):
        with connect_db() as conn:
            conn.execute("""
                INSERT INTO searches (query, created_at)
                VALUES (?, ?)
            """, (query, datetime.now().isoformat(timespec="seconds")))
        self.refresh_history()

    def search_sources(self):
        parts = self.current_query_parts()
        query = parts["query"]

        if not query:
            QMessageBox.information(
                self, "Search", "Enter at least one search criterion."
            )
            return

        sources = self.enabled_sources()
        if not sources:
            QMessageBox.information(
                self, "Search",
                "No enabled sources are configured. Open Manage Sources."
            )
            return

        self.results_table.setRowCount(0)
        jobs = []

        for source in sources:
            url = build_search_url(
                source["url_template"], query,
                parts["artist"], parts["title"],
                parts["label"], parts["catalog"]
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

            # Vinkje staat links van de knop Open Search.
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(8)

            positive_check = QCheckBox()
            positive_check.setEnabled(False)
            positive_check.setToolTip(
                "Wordt aangevinkt als de achtergrondcontrole "
                "positieve zoekresultaten bevestigt."
            )
            action_layout.addWidget(positive_check)

            open_button = QPushButton("Open Search")
            open_button.setMinimumSize(125, 30)
            open_button.setToolTip("Open this search in your browser")
            open_button.clicked.connect(
                lambda checked=False, target=url: webbrowser.open(target)
            )
            action_layout.addWidget(open_button)
            action_layout.addStretch(1)

            self.results_table.setCellWidget(row, 2, action_widget)
            self.results_table.setRowHeight(row, 42)

            # Voeg ook een statusitem toe als tooltip op de URL-cel.
            url_item.setToolTip(url + "\nControleren op zoekresultaten...")
            jobs.append((row, url, query))

        self.record_search(query)

        if not jobs:
            QMessageBox.information(
                self, "Search",
                "No valid search destinations were prepared. "
                "Check Manage Sources."
            )
            return

        self.statusBar().showMessage(
            f"Prepared {len(jobs)} searches; checking results in background..."
        )
        self.start_background_checks(jobs)

    def start_background_checks(self, jobs):
        if self.search_thread is not None:
            if self.search_thread.isRunning():
                QMessageBox.information(
                    self, "Search",
                    "A previous search verification is still running."
                )
                return

        self.search_jobs = jobs
        self.search_thread = QThread(self)
        self.search_worker = SearchWorker(jobs)
        self.search_worker.moveToThread(self.search_thread)

        self.search_thread.started.connect(self.search_worker.run)
        self.search_worker.result_ready.connect(self.on_search_result)
        self.search_worker.finished.connect(self.search_thread.quit)
        self.search_worker.finished.connect(self.search_worker.deleteLater)
        self.search_thread.finished.connect(self.on_search_checks_finished)
        self.search_thread.finished.connect(self.search_thread.deleteLater)

        self.search_thread.start()

    def on_search_result(self, row, positive, status):
        if row < 0 or row >= self.results_table.rowCount():
            return

        widget = self.results_table.cellWidget(row, 2)
        if widget:
            checkbox = widget.findChild(QCheckBox)
            if checkbox:
                checkbox.setChecked(bool(positive))
                checkbox.setToolTip(status)

        url_item = self.results_table.item(row, 1)
        if url_item:
            url_item.setToolTip(url_item.text() + "\n" + status)

        name_item = self.results_table.item(row, 0)
        name = name_item.text() if name_item else "Website"
        self.statusBar().showMessage(
            f"{name}: {status}", 8000
        )

    def on_search_checks_finished(self):
        positive_count = 0
        total = self.results_table.rowCount()

        for row in range(total):
            widget = self.results_table.cellWidget(row, 2)
            if widget:
                checkbox = widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    positive_count += 1

        self.statusBar().showMessage(
            f"Search verification complete: {positive_count} positive "
            f"result(s) out of {total} websites.",
            12000,
        )
        self.search_thread = None
        self.search_worker = None

    def clear_filters(self):
        for widget in (
            self.artist_edit, self.title_edit,
            self.label_edit, self.catalog_edit
        ):
            widget.clear()
        self.results_table.setRowCount(0)
        self.statusBar().showMessage("Filters cleared.")

    # -----------------------------------------------------
    # MANAGE SOURCES
    # -----------------------------------------------------

    def create_sources_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.sources_table = QTableWidget(0, 4)
        self.sources_table.setHorizontalHeaderLabels([
            "Select", "Name", "Search URL Template", "Enabled"
        ])
        self.configure_table(self.sources_table)
        self.sources_table.cellClicked.connect(self.toggle_source_at_row)

        header = self.sources_table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.sources_table, 1)

        country_row = QHBoxLayout()
        country_row.addWidget(QLabel("Generate webshop list for country:"))

        self.country_picklist = QComboBox()
        for name, code in EUROPEAN_COUNTRIES:
            self.country_picklist.addItem(name, code)
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
            ("Select All / Deselect All", self.toggle_select_all_sources),
            ("Export Sources to CSV", self.export_sources_csv),
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

    def toggle_select_all_sources(self):
        count = self.sources_table.rowCount()
        if not count:
            return
        all_selected = all(
            self.sources_table.item(row, 0)
            and self.sources_table.item(row, 0).checkState()
            == Qt.CheckState.Checked
            for row in range(count)
        )
        state = (
            Qt.CheckState.Unchecked
            if all_selected else Qt.CheckState.Checked
        )
        for row in range(count):
            item = self.sources_table.item(row, 0)
            if item:
                item.setCheckState(state)

    def export_sources_csv(self):
        with connect_db() as conn:
            rows = conn.execute("""
                SELECT name, url_template, enabled
                FROM sources ORDER BY name
            """).fetchall()

        if not rows:
            QMessageBox.information(
                self, "Export Sources", "There are no sources to export."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Current Sources",
            f"VinylFinder_sources_{datetime.now():%Y%m%d_%H%M%S}.csv",
            "CSV files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["name", "url_template", "enabled"]
                )
                writer.writeheader()
                for source in rows:
                    writer.writerow({
                        "name": source["name"],
                        "url_template": source["url_template"],
                        "enabled": int(source["enabled"]),
                    })
        except (OSError, csv.Error) as exc:
            QMessageBox.warning(self, "Export Sources", str(exc))
            return

        QMessageBox.information(
            self, "Export Sources",
            f"Exported {len(rows)} sources to:\n{path}"
        )

    def selected_source_ids(self):
        ids = []
        for row in range(self.sources_table.rowCount()):
            check = self.sources_table.item(row, 0)
            name_item = self.sources_table.item(row, 1)
            if (
                check and check.checkState() == Qt.CheckState.Checked
                and name_item
            ):
                source_id = name_item.data(Qt.ItemDataRole.UserRole)
                if source_id is not None:
                    ids.append(source_id)
        return ids

    def selected_source_id(self):
        row = self.sources_table.currentRow()
        if row < 0:
            return None
        item = self.sources_table.item(row, 1)
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

            check = QTableWidgetItem("")
            check.setFlags(
                (check.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                & ~Qt.ItemFlag.ItemIsEditable
            )
            check.setCheckState(Qt.CheckState.Unchecked)
            self.sources_table.setItem(row, 0, check)

            name = QTableWidgetItem(source["name"])
            name.setData(Qt.ItemDataRole.UserRole, source["id"])
            self.sources_table.setItem(row, 1, name)
            self.sources_table.setItem(
                row, 2, QTableWidgetItem(source["url_template"])
            )
            self.sources_table.setItem(
                row, 3,
                QTableWidgetItem("Yes" if source["enabled"] else "No")
            )

    def add_source(self):
        dialog = SourceDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, url, enabled = dialog.values()
        try:
            with connect_db() as conn:
                conn.execute("""
                    INSERT INTO sources (name, url_template, enabled)
                    VALUES (?, ?, ?)
                """, (name, url, enabled))
        except sqlite3.IntegrityError as exc:
            QMessageBox.warning(self, "Source Error", str(exc))
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
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        if not source:
            return

        dialog = SourceDialog(self, source)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, url, enabled = dialog.values()

        with connect_db() as conn:
            conn.execute("""
                UPDATE sources
                SET name = ?, url_template = ?, enabled = ?
                WHERE id = ?
            """, (name, url, enabled, source_id))
        self.refresh_sources()

    def toggle_source_at_row(self, row, column):
        if column != 3:
            return
        item = self.sources_table.item(row, 1)
        if not item:
            return
        source_id = item.data(Qt.ItemDataRole.UserRole)
        if source_id is None:
            return
        with connect_db() as conn:
            conn.execute(
                "UPDATE sources SET enabled = 1 - enabled WHERE id = ?",
                (source_id,)
            )
        self.refresh_sources()

    def toggle_source(self):
        ids = self.selected_source_ids()
        if not ids:
            QMessageBox.information(
                self, "Sources", "Tick at least one source first."
            )
            return
        with connect_db() as conn:
            conn.executemany(
                "UPDATE sources SET enabled = 1 - enabled WHERE id = ?",
                [(source_id,) for source_id in ids]
            )
        self.refresh_sources()

    def delete_source(self):
        ids = self.selected_source_ids()
        if not ids:
            source_id = self.selected_source_id()
            if source_id is not None:
                ids = [source_id]

        if not ids:
            QMessageBox.information(
                self, "Sources", "Select at least one source first."
            )
            return

        answer = QMessageBox.question(
            self, "Delete Source",
            f"Permanently remove {len(ids)} selected source(s)?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        with connect_db() as conn:
            conn.executemany(
                "DELETE FROM sources WHERE id = ?",
                [(source_id,) for source_id in ids]
            )
        self.refresh_sources()

    # -----------------------------------------------------
    # SEARCH WEB SITES ONLINE
    # -----------------------------------------------------

    def search_websites_online(self):
        country = self.country_picklist.currentText()

        country_queries = {
            "Italy": "negozio online vinili CD compra dischi vinile",
            "Netherlands": "online platenwinkel vinyl platen cd webshop",
            "Germany": "Online Schallplatten Shop Vinyl CDs",
            "France": "boutique en ligne disques vinyles CD",
            "Spain": "tienda online discos vinilo CD",
            "United Kingdom": "online record shop vinyl records CDs",
        }
        query = country_queries.get(
            country, f"online record shop vinyl records CDs {country}"
        )
        search_terms = [
            query,
            f'"vinyl records" "online shop" {country}',
            f"record store vinyl CDs webshop {country}",
        ]

        candidates = []
        errors = []

        for term in search_terms:
            search_url = (
                "https://html.duckduckgo.com/html/?q=" + quote_plus(term)
            )
            request = urllib.request.Request(
                search_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/130 Safari/537.36"
                    )
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=12) as response:
                    html = response.read(1500000).decode(
                        "utf-8", errors="ignore"
                    )
                parser = DuckDuckGoResultsParser()
                parser.feed(html)

                for result in parser.results:
                    url = result["url"]
                    if "duckduckgo.com/l/" in url:
                        values = parse_qs(urlparse(url).query).get("uddg", [])
                        if values:
                            url = unquote(values[0])

                    if not valid_http_url(url):
                        continue

                    host = urlparse(url).netloc.lower()
                    excluded = (
                        "duckduckgo.com", "google.com", "bing.com",
                        "youtube.com", "spotify.com", "soundcloud.com",
                        "deezer.com", "tidal.com", "music.apple.com",
                    )
                    if any(domain in host for domain in excluded):
                        continue

                    candidates.append({
                        "name": result["title"][:100],
                        "url": url,
                    })
            except Exception as exc:
                errors.append(str(exc)[:120])

        for name, template in COUNTRY_SHOP_CANDIDATES.get(country, []):
            parsed = urlparse(template)
            base = f"{parsed.scheme}://{parsed.netloc}"
            if valid_http_url(base):
                candidates.append({"name": name, "url": base})

        country_code = self.country_picklist.currentData()
        ebay_domain = EBAY_DOMAINS.get(country_code, "www.ebay.com")
        candidates.extend([
            {"name": "Discogs", "url": "https://www.discogs.com"},
            {"name": "eBay", "url": f"https://{ebay_domain}"},
        ])

        unique = []
        seen = set()
        for candidate in candidates:
            parsed = urlparse(candidate["url"])
            base = f"{parsed.scheme}://{parsed.netloc}"
            key = base.casefold()
            if not base or key in seen:
                continue
            seen.add(key)
            candidate["url"] = base
            unique.append(candidate)

        if not unique:
            message = "No website candidates were found."
            if errors:
                message += "\n\n" + "\n".join(errors[:3])
            QMessageBox.warning(self, "Search Websites", message)
            return

        dialog = CountryWebsiteResultsDialog(country, unique, self)
        dialog.exec()

    # -----------------------------------------------------
    # GENERATE COUNTRY CSV
    # -----------------------------------------------------

    def generate_country_sources_csv(self):
        country = self.country_picklist.currentText()
        country_code = self.country_picklist.currentData()

        path, _ = QFileDialog.getSaveFileName(
            self, f"Save tested webshop list for {country}",
            f"VinylFinder_{country.replace(' ', '_')}_sources.csv",
            "CSV files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        ebay_domain = EBAY_DOMAINS.get(country_code, "www.ebay.com")
        candidates = [
            ("Discogs", "https://www.discogs.com/search/?q={query}&type=all"),
            ("eBay", f"https://{ebay_domain}/sch/i.html?_nkw={{query}}"),
            ("Bandcamp", "https://bandcamp.com/search?q={query}"),
        ]
        candidates.extend(COUNTRY_SHOP_CANDIDATES.get(country, []))

        unique = []
        seen = set()
        for name, template in candidates:
            key = (name.casefold(), template.casefold())
            if key not in seen:
                seen.add(key)
                unique.append((name, template))

        query = "vinile" if country == "Italy" else "vinyl"
        passed = []
        failed = []
        tested_at = datetime.now().isoformat(timespec="seconds")

        progress = QProgressDialog(
            "Testing search URLs...", "Cancel", 0, len(unique), self
        )
        progress.setWindowTitle("Generate Country CSV")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)

        try:
            for index, (name, template) in enumerate(unique, start=1):
                progress.setLabelText(f"Testing {name} ({index}/{len(unique)})")
                progress.setValue(index - 1)
                QApplication.processEvents()

                if progress.wasCanceled():
                    break

                url = build_search_url(template, query)
                if not url:
                    failed.append((name, "invalid search template"))
                    continue

                positive, status = check_search_result(url, query)
                if positive:
                    passed.append({
                        "name": name,
                        "url_template": template,
                        "enabled": 1,
                        "country": country,
                        "test_query": query,
                        "test_status": status,
                        "test_url": url,
                        "tested_at": tested_at,
                    })
                else:
                    failed.append((name, status))
        finally:
            progress.close()
            progress.deleteLater()

        fields = [
            "name", "url_template", "enabled", "country",
            "test_query", "test_status", "test_url", "tested_at",
        ]
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(passed)
        except OSError as exc:
            QMessageBox.warning(self, "Country CSV", str(exc))
            return

        QMessageBox.information(
            self, "Country CSV Generated",
            f"Country: {country}\n"
            f"Positive search tests: {len(passed)}\n"
            f"Not confirmed: {len(failed)}\n\n"
            f"Saved CSV:\n{path}"
        )

    # -----------------------------------------------------
    # IMPORT SOURCES CSV
    # -----------------------------------------------------

    def import_sources_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Sources from CSV", "",
            "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return

        imported = skipped = invalid = 0
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel

                reader = csv.DictReader(f, dialect=dialect)
                if not reader.fieldnames:
                    QMessageBox.warning(
                        self, "CSV Import", "CSV has no header row."
                    )
                    return

                reader.fieldnames = [
                    (name or "").strip().lower()
                    for name in reader.fieldnames
                ]
                if not {"name", "url_template"}.issubset(reader.fieldnames):
                    QMessageBox.warning(
                        self, "CSV Import",
                        "Required columns: name, url_template."
                    )
                    return

                with connect_db() as conn:
                    for item in reader:
                        name = (item.get("name") or "").strip()
                        template = (item.get("url_template") or "").strip()
                        enabled_text = (
                            item.get("enabled") or "1"
                        ).strip().lower()

                        if not name or not template or not validate_template(template):
                            invalid += 1
                            continue

                        if enabled_text in ("1", "true", "yes", "enabled"):
                            enabled = 1
                        elif enabled_text in ("0", "false", "no", "disabled"):
                            enabled = 0
                        else:
                            invalid += 1
                            continue

                        exists = conn.execute("""
                            SELECT 1 FROM sources
                            WHERE lower(name) = lower(?)
                        """, (name,)).fetchone()
                        if exists:
                            skipped += 1
                            continue

                        conn.execute("""
                            INSERT INTO sources (name, url_template, enabled)
                            VALUES (?, ?, ?)
                        """, (name, template, enabled))
                        imported += 1

            self.refresh_sources()
            QMessageBox.information(
                self, "CSV Import Complete",
                f"Imported: {imported}\nSkipped: {skipped}\nInvalid: {invalid}"
            )
        except (OSError, csv.Error, UnicodeError) as exc:
            QMessageBox.critical(
                self, "CSV Import Failed", str(exc)
            )

    # -----------------------------------------------------
    # FAVORITES
    # -----------------------------------------------------

    def create_favorites_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.favorites_table = QTableWidget(0, 3)
        self.favorites_table.setHorizontalHeaderLabels(
            ["Title", "URL", "Notes"]
        )
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
            rows = conn.execute("""
                SELECT * FROM favorites ORDER BY created_at DESC
            """).fetchall()

        self.favorites_table.setRowCount(0)
        for fav in rows:
            row = self.favorites_table.rowCount()
            self.favorites_table.insertRow(row)

            title = QTableWidgetItem(fav["title"])
            title.setData(Qt.ItemDataRole.UserRole, fav["id"])
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
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def add_favorite(self):
        dialog = FavoriteDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title, url, notes = dialog.values()

        try:
            with connect_db() as conn:
                conn.execute("""
                    INSERT INTO favorites (title, url, notes, created_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    title, url, notes,
                    datetime.now().isoformat(timespec="seconds")
                ))
        except sqlite3.IntegrityError:
            QMessageBox.information(
                self, "Favorites", "This URL is already a favorite."
            )
            return
        self.refresh_favorites()

    def open_selected_favorite(self):
        row = self.favorites_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Favorites", "Select a favorite first."
            )
            return
        item = self.favorites_table.item(row, 1)
        if item and valid_http_url(item.text()):
            webbrowser.open(item.text())

    def delete_favorite(self):
        fav_id = self.selected_favorite_id()
        if fav_id is None:
            QMessageBox.information(
                self, "Favorites", "Select a favorite first."
            )
            return

        answer = QMessageBox.question(
            self, "Remove Favorite", "Remove the selected favorite?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        with connect_db() as conn:
            conn.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))
        self.refresh_favorites()

    # -----------------------------------------------------
    # SEARCH HISTORY
    # -----------------------------------------------------

    def create_history_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.history_table = QTableWidget(0, 2)
        self.history_table.setHorizontalHeaderLabels(
            ["Search Query", "Date / Time"]
        )
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
            rows = conn.execute("""
                SELECT * FROM searches ORDER BY id DESC LIMIT 500
            """).fetchall()

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
            self, "Clear History", "Delete all saved search history?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        with connect_db() as conn:
            conn.execute("DELETE FROM searches")
        self.refresh_history()


# =========================================================
# APPLICATION ENTRY POINT
# =========================================================

def main():
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { background-color: #000000; color: #ffffff; }
        QMainWindow, QDialog, QTabWidget::pane, QScrollArea {
            background-color: #000000; color: #ffffff;
        }
        QLabel { background-color: transparent; color: #ffffff; }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
        QSpinBox, QDoubleSpinBox {
            background-color: #111111; color: #ffffff;
            selection-background-color: #3d5f86;
            selection-color: #ffffff; border: 1px solid #666666;
            padding: 4px;
        }
        QComboBox QAbstractItemView {
            background-color: #111111; color: #ffffff;
            selection-background-color: #3d5f86;
            selection-color: #ffffff;
        }
        QPushButton {
            background-color: #292929; color: #ffffff;
            border: 1px solid #666666; border-radius: 3px;
            padding: 6px 10px;
        }
        QPushButton:hover { background-color: #3b3b3b; }
        QPushButton:pressed {
            background-color: #3d5f86; color: #ffffff;
        }
        QPushButton:disabled {
            background-color: #181818; color: #888888;
            border-color: #444444;
        }
        QTabBar::tab {
            background-color: #202020; color: #ffffff;
            padding: 8px 12px; border: 1px solid #555555;
        }
        QTabBar::tab:selected {
            background-color: #3d5f86; color: #ffffff;
        }
        QHeaderView::section {
            background-color: #292929; color: #ffffff;
            border: 1px solid #555555; padding: 5px;
        }
        QStatusBar { background-color: #111111; color: #ffffff; }
        QMenu, QMenuBar {
            background-color: #111111; color: #ffffff;
            border: 1px solid #555555;
        }
        QMenu::item:selected {
            background-color: #3d5f86; color: #ffffff;
        }
        QCheckBox { background-color: transparent; color: #ffffff; }
        QProgressDialog, QMessageBox {
            background-color: #000000; color: #ffffff;
        }
    """)

    window = VinylFinder()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
