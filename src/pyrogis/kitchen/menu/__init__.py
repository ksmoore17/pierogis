from .menu_item import MenuItem
from .custom_order import CustomOrder
from .quantize_order import QuantizeOrder
from .sort_order import SortOrder
from .threshold_order import ThresholdOrder
from .resize_order import ResizeOrder
from .rotate_order import RotateOrder

menu = {
    SortOrder.type_name: SortOrder,
    QuantizeOrder.type_name: QuantizeOrder,
    'chef': CustomOrder,
    ThresholdOrder.type_name: ThresholdOrder,
    ResizeOrder.type_name: ResizeOrder,
    'rotate': RotateOrder
}
