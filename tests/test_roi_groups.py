import unittest

from roi_groups import class_index_for_region, group_roi_regions


class SelectionClassGroupingTests(unittest.TestCase):
    def test_repeated_color_is_one_class_with_independent_eye_regions(self):
        regions = [
            {'left_rect': (1, 2, 3, 4), 'right_rect': None,
             'metadata': {'TARGET': 'A'}},
            {'left_rect': None, 'right_rect': (5, 6, 7, 8)},
            {'left_rect': (9, 10, 2, 2), 'right_rect': (11, 12, 2, 2)},
        ]
        groups = group_roi_regions(
            regions,
            [(255, 0, 0), (255, 0, 0), (0, 255, 0)],
            ['red', 'red', 'green'],
        )

        self.assertEqual([group['name'] for group in groups], ['red', 'green'])
        self.assertEqual(groups[0]['indices'], [0, 1])
        self.assertEqual(groups[0]['left_rects'], [(1, 2, 3, 4)])
        self.assertEqual(groups[0]['right_rects'], [(5, 6, 7, 8)])
        self.assertEqual(groups[0]['metadata'], {'TARGET': 'A'})
        self.assertEqual(class_index_for_region(groups, 1), 0)
        self.assertEqual(class_index_for_region(groups, 2), 1)


if __name__ == '__main__':
    unittest.main()
