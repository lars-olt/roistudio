import numpy as np
from PyQt5.QtGui import QImage, QPixmap


def numpy_to_pixmap(img_array):
    """Convert a numpy array to a QPixmap."""
    img_array = np.ascontiguousarray(img_array)
    img_array = np.nan_to_num(img_array, nan=0.0, posinf=1.0, neginf=0.0)

    if img_array.dtype != np.uint8:
        if img_array.max() <= 1.0:
            img_array = (img_array * 255).astype(np.uint8)
        else:
            img_min = img_array.min()
            img_max = img_array.max()
            if img_max > img_min:
                img_array = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)
            else:
                img_array = np.zeros_like(img_array, dtype=np.uint8)

    height, width = img_array.shape[:2]
    q_image = QImage(img_array.data, width, height, 3 * width, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(q_image)


def hex_to_rgb(hex_color):
    """Convert a hex color string to an RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))