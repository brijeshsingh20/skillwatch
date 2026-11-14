"""Frame quality score in [0, 1] from edge strength and contrast (explainable, no ML)."""
import cv2
import numpy as np

EDGE_REF = 260.0      # 99th-percentile Sobel magnitude of a healthy frame at 320 px width
CONTRAST_REF = 22.0   # grey-level standard deviation of a healthy frame


def frame_quality(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if w != 320:  # normalise so the score does not depend on the sampling width
        gray = cv2.resize(gray, (320, max(1, int(h * 320 / w))), interpolation=cv2.INTER_AREA)
    smooth = cv2.GaussianBlur(gray, (3, 3), 0)  # suppress sensor noise before measuring edges
    gx = cv2.Sobel(smooth, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(smooth, cv2.CV_32F, 0, 1)
    edge = float(np.percentile(np.hypot(gx, gy), 99))
    contrast = float(gray.std())
    score = 0.6 * min(1.0, edge / EDGE_REF) + 0.4 * min(1.0, contrast / CONTRAST_REF)
    return round(max(0.0, min(1.0, score)), 3)
