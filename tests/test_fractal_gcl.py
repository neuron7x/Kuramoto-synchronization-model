import warnings

import networkx as nx
import numpy as np

from core.indicators.fractal_gcl import fd_one_shot, fractal_boxcover


def test_fd_one_shot_stable_no_warning():
    graph = nx.path_graph(8)
    boxes = fractal_boxcover(graph, max_box=2)
    with warnings.catch_warnings(record=True) as caught:
        dimension = fd_one_shot(graph, boxes)
    assert caught == []
    assert np.isfinite(dimension)
    assert dimension >= 0.0


def test_fd_one_shot_flat_configuration():
    graph = nx.cycle_graph(6)
    boxes = [[node] for node in graph.nodes()]
    assert fd_one_shot(graph, boxes) == 0.0
