from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap


def visualize_rois_on_image(rgb_pixmap, rois_data, color_list):
    """Overlays ROIs on image and returns new pixmap."""
    if rgb_pixmap is None:
        return None
    
    image = rgb_pixmap.toImage()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    
    for i, roi_data in enumerate(rois_data):
        color = color_list[i % len(color_list)]
        x, y, w, h = roi_data['roi']
        
        qcolor = QColor(*color, 80)
        painter.setPen(QPen(QColor(*color), 2))
        painter.setBrush(qcolor)
        painter.drawRect(x, y, w, h)
    
    painter.end()
    return QPixmap.fromImage(image)