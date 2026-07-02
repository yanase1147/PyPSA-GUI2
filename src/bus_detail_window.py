from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QGroupBox, QFormLayout, QAbstractItemView,
)

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from .models import Area, Generator, Load, CARRIER_COLORS


def _fmt(v) -> str:
    """Format a value for table display: floats drop unnecessary trailing zeros."""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


class AreaDetailWindow(QDialog):
    def __init__(self, area: Area, generators, loads, parent=None):
        super().__init__(parent)
        self.area       = area
        self.generators = generators
        self.loads      = loads
        self.setWindowTitle(self.tr("エリア詳細: {}").format(area.name))
        self.setMinimumSize(720, 540)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info_group = QGroupBox(self.tr("エリア情報"))
        info_form  = QFormLayout(info_group)
        info_form.addRow(self.tr("名前:"), QLabel(self.area.name))
        info_form.addRow(self.tr("緯度:"), QLabel(f"{self.area.lat:.6f}"))
        info_form.addRow(self.tr("経度:"), QLabel(f"{self.area.lon:.6f}"))
        info_form.addRow(self.tr("国:"), QLabel(self.area.country or "—"))
        layout.addWidget(info_group)

        tabs = QTabWidget()

        # ── Generation ────────────────────────────────────────────────
        gen_tab = QWidget()
        gen_lay = QVBoxLayout(gen_tab)
        if HAS_MPL and self.generators:
            gen_lay.addWidget(self._gen_chart())
        gen_table = self._plain_table(
            [self.tr("名前"), self.tr("種別"), self.tr("容量(MW)"), self.tr("変動費(Currency/MWh)"), self.tr("建設費(Currency/MW)"), self.tr("効率")])
        for g in self.generators:
            r = gen_table.rowCount(); gen_table.insertRow(r)
            for c, v in enumerate([g.name, g.carrier, g.p_nom,
                                    g.marginal_cost, g.capital_cost, g.efficiency]):
                gen_table.setItem(r, c, QTableWidgetItem(_fmt(v)))
        gen_lay.addWidget(gen_table)
        total_cap = sum(g.p_nom for g in self.generators)
        gen_lay.addWidget(QLabel(self.tr("合計設備容量: {:,.1f} MW").format(total_cap)))
        tabs.addTab(gen_tab, self.tr("発電"))

        # ── Demand ────────────────────────────────────────────────────
        dem_tab = QWidget()
        dem_lay = QVBoxLayout(dem_tab)
        if HAS_MPL and self.loads and sum(l.p_set for l in self.loads) > 0:
            dem_lay.addWidget(self._demand_chart())
        dem_table = self._plain_table([self.tr("名前"), self.tr("需要(MW)")])
        for ld in self.loads:
            r = dem_table.rowCount(); dem_table.insertRow(r)
            dem_table.setItem(r, 0, QTableWidgetItem(ld.name))
            dem_table.setItem(r, 1, QTableWidgetItem(_fmt(ld.p_set)))
        dem_lay.addWidget(dem_table)
        total_dem = sum(l.p_set for l in self.loads)
        dem_lay.addWidget(QLabel(self.tr("合計需要: {:,.1f} MW").format(total_dem)))
        tabs.addTab(dem_tab, self.tr("需要"))

        layout.addWidget(tabs)

    @staticmethod
    def _plain_table(headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return t

    def _gen_chart(self):
        carrier_caps: dict = {}
        for g in self.generators:
            carrier_caps[g.carrier] = carrier_caps.get(g.carrier, 0) + g.p_nom

        fig = Figure(figsize=(6, 2.8), dpi=90, tight_layout=True)
        ax  = fig.add_subplot(111)
        carriers = list(carrier_caps)
        values   = [carrier_caps[c] for c in carriers]
        colors   = [CARRIER_COLORS.get(c.split("(")[0], "#aaaaaa") for c in carriers]
        ax.bar(carriers, values, color=colors, edgecolor="white")
        ax.set_ylabel(self.tr("設備容量 (MW)"))
        ax.set_title(self.tr("電源別設備容量"))
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(40); lbl.set_ha("right")
        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(210)
        return canvas

    def _demand_chart(self):
        names  = [l.name  for l in self.loads]
        values = [l.p_set for l in self.loads]
        fig = Figure(figsize=(4, 2.8), dpi=90, tight_layout=True)
        ax  = fig.add_subplot(111)
        ax.pie(values, labels=names, autopct="%1.1f%%", startangle=90)
        ax.set_title(self.tr("需要の内訳"))
        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(210)
        return canvas
