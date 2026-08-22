"""Group independently editable ROI regions into color selection classes."""


def group_roi_regions(rois_data, colors, color_names):
    """Return selection classes in first-appearance order.

    Each ROI entry remains independently editable. Entries with the same color
    name belong to one selection class and share metadata, spectra, and export
    masks.
    """
    groups = []
    by_name = {}

    for index, roi in enumerate(rois_data):
        name = color_names[index] if index < len(color_names) else f'ROI_{index + 1}'
        color = colors[index] if index < len(colors) else (255, 255, 255)
        group = by_name.get(name)
        if group is None:
            group = {
                'name': name,
                'color': color,
                'indices': [],
                'regions': [],
                'left_rects': [],
                'right_rects': [],
                'metadata': {},
            }
            by_name[name] = group
            groups.append(group)

        group['indices'].append(index)
        group['regions'].append(roi)
        if roi.get('left_rect') is not None:
            group['left_rects'].append(tuple(roi['left_rect']))
        if roi.get('right_rect') is not None:
            group['right_rects'].append(tuple(roi['right_rect']))
        if not group['metadata'] and roi.get('metadata'):
            group['metadata'] = dict(roi['metadata'])

    return groups


def class_index_for_region(groups, region_index):
    """Return the selection-class index containing a flattened region index."""
    return next(
        (index for index, group in enumerate(groups)
         if region_index in group['indices']),
        None,
    )
