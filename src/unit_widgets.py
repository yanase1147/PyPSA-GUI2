"""容量(MW)・エネルギー容量(MWh)入力欄向けの単位切替ウィジェット。

内部の正準値は常にMW（power）/MWh（energy）で保持し、表示単位のみを
コンボボックスで切り替える。呼び出し側（各ダイアログの _prefill/get_xxx）は
.value()/.setValue() を通じて常に正準値（MW/MWh）だけを扱えばよい。
"""
import math

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QDoubleSpinBox, QComboBox

POWER_UNITS = ["W", "kW", "MW", "GW"]
POWER_FACTORS = {"W": 1e6, "kW": 1e3, "MW": 1.0, "GW": 1e-3}

ENERGY_UNITS = ["Wh", "kWh", "MWh", "GWh", "PJ", "toe"]
ENERGY_FACTORS = {
    "Wh": 1e6, "kWh": 1e3, "MWh": 1.0, "GWh": 1e-3,
    "PJ": 1.0 / 277777.77778,   # 1 PJ = 277,777.78 MWh
    "toe": 1.0 / 11.63,         # 1 toe = 11.63 MWh
}

_CANONICAL_UNIT = {"power": "MW", "energy": "MWh"}
_UNITS = {"power": POWER_UNITS, "energy": ENERGY_UNITS}
_FACTORS = {"power": POWER_FACTORS, "energy": ENERGY_FACTORS}


class _AdaptiveDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that hides trailing zeros in the display."""
    def textFromValue(self, value: float) -> str:
        return f"{value:g}"


class UnitValueBox(QWidget):
    """スピンボックス＋単位選択コンボの複合ウィジェット。

    .value()/.setValue() は常に正準単位（power→MW, energy→MWh）で
    やり取りする。表示単位を切り替えても値は保持されたまま換算される。
    """

    def __init__(self, family: str, lo: float = 0.0, hi: float = 1e9,
                 val: float = 0.0, step: float = None, decimals: int = 2,
                 parent=None):
        super().__init__(parent)
        self._family = family
        self._units = _UNITS[family]
        self._factors = _FACTORS[family]
        self._canonical_unit = _CANONICAL_UNIT[family]
        self._base_lo = lo
        self._base_hi = hi
        self._base_decimals = decimals
        self._current_unit = self._canonical_unit

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.spin = _AdaptiveDoubleSpinBox()
        if step is not None:
            self.spin.setSingleStep(step)

        self.combo = QComboBox()
        self.combo.addItems(self._units)
        self.combo.setCurrentText(self._canonical_unit)
        self.combo.setFixedWidth(64)

        layout.addWidget(self.spin, 1)
        layout.addWidget(self.combo)

        self._apply_range_for_unit(self._canonical_unit)
        self.spin.setValue(val * self._factors[self._canonical_unit])

        self.combo.currentTextChanged.connect(self._on_unit_changed)

    def _decimals_for_unit(self, unit: str) -> int:
        """Widen decimals for units with a small canonical->displayed factor
        (e.g. PJ, toe) so small displayed values don't round away to 0."""
        factor = self._factors[unit]
        if factor >= 1:
            return self._base_decimals
        return self._base_decimals + math.ceil(-math.log10(factor))

    def _apply_range_for_unit(self, unit: str) -> None:
        factor = self._factors[unit]
        self.spin.setDecimals(self._decimals_for_unit(unit))
        self.spin.setRange(self._base_lo * factor, self._base_hi * factor)

    def _on_unit_changed(self, new_unit: str) -> None:
        canonical = self.value()
        self._apply_range_for_unit(new_unit)
        self.spin.setValue(canonical * self._factors[new_unit])
        self._current_unit = new_unit

    def value(self) -> float:
        return self.spin.value() / self._factors[self._current_unit]

    def setValue(self, canonical_value: float) -> None:
        self.spin.setValue(canonical_value * self._factors[self._current_unit])
