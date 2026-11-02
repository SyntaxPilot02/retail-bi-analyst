"""Original visual layout only; workflows are in the controller and services."""
from __future__ import annotations

# import PySide6 Qt GUI widgets
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QLabel,
    QPushButton,
    QComboBox,
    QDateEdit,
    QTabWidget,
    QTextEdit,
)
# import Core Qt constants and QDate date type
from PySide6.QtCore import Qt, QDate
# import Qt GUI classes for standard item model, text options and screen information
from PySide6.QtGui import (
    QAction,
    QTextOption,
    QGuiApplication,
)

# import Matplotlib Qt canvas backend integration
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
# import Matplotlib Figure container class
from matplotlib.figure import Figure

# import internal application modules and data loaders
from src.config import APP_NAME
from visualization.graphs import GraphDataChoice, GraphType


class MainWindowView(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            size = screen.availableGeometry()
            self.resize(int(size.width() * 0.7), int(size.height() * 0.7))
        self._init_menu()
        self._init_ui()

    def _init_menu(self) -> None:
        """
        Initialize the menu bar.
        """
        # get window menubar pointer
        menubar = self.menuBar()

        # add top-level "File" menu
        file_menu = menubar.addMenu("&File")

        # create menu item for importing CSV files
        import_csv_action = QAction("Import CSV", self)
        self.import_csv_action = import_csv_action
        # add action to File menu
        file_menu.addAction(import_csv_action)

        # create menu item for importing SQLite databases
        import_db_action = QAction("Import SQLite DB", self)
        self.import_sqlite_action = import_db_action
        # add action to File menu
        file_menu.addAction(import_db_action)

        # create menu item to exit application
        exit_action = QAction("Exit", self)
        self.exit_action = exit_action
        # add action to File menu
        file_menu.addAction(exit_action)

        # add top-level "Report" menu
        report_menu = menubar.addMenu("&Report")

        # create menu action to generate and save Markdown report
        generate_report_action = QAction("Generate Markdown Report", self)
        self.gen_report_action = generate_report_action
        # add action to Report menu
        report_menu.addAction(generate_report_action)

        # create menu action to generate interactive HTML report dashboard
        generate_html_action = QAction("Generate HTML Report", self)
        self.gen_html_report_action = generate_html_action
        # add action to Report menu
        report_menu.addAction(generate_html_action)

    # ------------------ UI -------------------

    # build main user interface layout and tabs
    def _init_ui(self) -> None:
        """
        Initialize the UI components.
        """
        # create central container widget
        central = QWidget(self)
        # apply horizontal layout to central widget
        main_layout = QHBoxLayout(central)

        # left side panel for input filters
        filters_layout = QVBoxLayout()

        # add filter section header label
        filters_layout.addWidget(QLabel("Filters"))

        # initialize start date picker widget
        self.date_from_edit = QDateEdit()
        # enable popup calendar selector
        self.date_from_edit.setCalendarPopup(True)
        # default start date to one month prior to current date
        self.date_from_edit.setDate(QDate.currentDate().addMonths(-1))

        # initialize end date picker widget
        self.date_to_edit = QDateEdit()
        # enable popup calendar selector
        self.date_to_edit.setCalendarPopup(True)
        # default end date to current date
        self.date_to_edit.setDate(QDate.currentDate())

        # add start date label and picker widget to side layout
        filters_layout.addWidget(QLabel("Date from"))
        filters_layout.addWidget(self.date_from_edit)
        # add end date label and picker widget to side layout
        filters_layout.addWidget(QLabel("Date to"))
        filters_layout.addWidget(self.date_to_edit)

        # initialize product category dropdown combobox
        self.category_combo = QComboBox()
        # add default placeholder item representing all categories
        self.category_combo.addItem("All Categories", userData=None)
        # add label and category combo to side layout
        filters_layout.addWidget(QLabel("Product category"))
        filters_layout.addWidget(self.category_combo)

        # initialize customer dropdown combobox
        self.customer_combo = QComboBox()
        # add default placeholder item representing all customers
        self.customer_combo.addItem("All Customers", userData=None)
        # add label and customer combo to side layout
        filters_layout.addWidget(QLabel("Customer"))
        filters_layout.addWidget(self.customer_combo)

        # button to trigger filter application
        apply_filters_btn = QPushButton("Apply Filters")
        self.apply_filters_btn = apply_filters_btn
        # add button to filter layout
        filters_layout.addWidget(apply_filters_btn)

        # button to reset all filter settings to default values
        reset_filters_btn = QPushButton("Reset Filters")
        self.reset_filters_btn = reset_filters_btn
        # add reset button to filter layout
        filters_layout.addWidget(reset_filters_btn)

        # add expanding vertical space pushing filter elements upward
        filters_layout.addStretch(1)

        # right side container - tabbed navigation panel
        self.tabs = QTabWidget()

        # --- Data Tab (Tabular Dataset View) ---
        self.data_table = QTableView()
        # Enable dynamic column sorting
        self.data_table.setSortingEnabled(True)

        # create tab widget for raw data view
        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        # add data table widget to layout
        data_layout.addWidget(self.data_table)
        # add Data tab to tab container widget
        self.tabs.addTab(data_tab, "Data")

        # --- Analytics Tab (KPI & RFM summary tables) ---
        self.kpi_table = QTableView()
        self.kpi_table.setSortingEnabled(True)

        self.rfm_table = QTableView()
        self.rfm_table.setSortingEnabled(True)

        # container widget for analytics tab
        analytics_tab = QWidget()
        analytics_layout = QVBoxLayout(analytics_tab)

        # KPI section title header
        kpi_title = QLabel("KPI summary")
        kpi_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        analytics_layout.addWidget(kpi_title)
        analytics_layout.addWidget(self.kpi_table)

        # RFM section title header
        rfm_title = QLabel("RFM analysis")
        rfm_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        analytics_layout.addWidget(rfm_title)
        analytics_layout.addWidget(self.rfm_table)

        # add Analytics tab to main tab widget
        self.tabs.addTab(analytics_tab, "Analytics")

        # --- Report Tab (Markdown analytical document preview) ---
        self.report_view = QTextEdit()
        # make text view read-only
        self.report_view.setReadOnly(True)
        # configure text word wrap behavior without horizontal scrollbar
        self.report_view.setWordWrapMode(QTextOption.WrapMode.WordWrap)

        # container for report tab
        report_tab = QWidget()
        report_layout = QVBoxLayout(report_tab)
        report_layout.addWidget(self.report_view)
        # add Report tab to tab container
        self.tabs.addTab(report_tab, "Report")

        # --- Graphs Tab (Interactive Matplotlib charts view) ---
        self.graph_data_combo = QComboBox()
        # populate metric dataset selection dropdown
        self.graph_data_combo.addItems(
            [
                GraphDataChoice.REVENUE_BY_DATE,
                GraphDataChoice.REVENUE_BY_CATEGORY,
                GraphDataChoice.CUSTOMERS_BY_SEGMENT,
            ]
        )

        self.graph_type_combo = QComboBox()
        # populate chart style type dropdown
        self.graph_type_combo.addItems(
            [
                GraphType.LINE,
                GraphType.BAR,
                GraphType.PIE,
            ]
        )

        # create Matplotlib Qt canvas instance
        self.graph_canvas = FigureCanvas(Figure(figsize=(6, 4)))
        # add subplot axes to figure
        self.graph_axes = self.graph_canvas.figure.add_subplot(111)

        # container widget for graphs tab
        graphs_tab = QWidget()
        graphs_layout = QVBoxLayout(graphs_tab)
        self.graphs_layout = graphs_layout

        # add graph choices UI elements to layout
        graphs_layout.addWidget(QLabel("Data for visualization"))
        graphs_layout.addWidget(self.graph_data_combo)

        graphs_layout.addWidget(QLabel("Chart type"))
        graphs_layout.addWidget(self.graph_type_combo)

        # place plot canvas in center stretching to fill space
        graphs_layout.addWidget(self.graph_canvas, stretch=1)

        # create action buttons row for graph tab
        graph_buttons_layout = QHBoxLayout()
        build_graph_btn = QPushButton("Build")
        self.build_graph_btn = build_graph_btn
        save_graph_btn = QPushButton("Save")
        self.save_graph_btn = save_graph_btn
        graph_buttons_layout.addStretch(1)
        graph_buttons_layout.addWidget(build_graph_btn)
        graph_buttons_layout.addWidget(save_graph_btn)
        graph_buttons_layout.addStretch(1)

        graphs_layout.addLayout(graph_buttons_layout)

        # add Graphs tab to tab panel
        self.tabs.addTab(graphs_tab, "Graphs")

        # assemble main window horizontal layout proportions
        main_layout.addLayout(filters_layout, 1)
        main_layout.addWidget(self.tabs, 3)

        # set central widget
        self.setCentralWidget(central)

