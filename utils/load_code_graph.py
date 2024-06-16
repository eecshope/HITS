import logging
from typing import List, Tuple

import networkx as nx
from networkx import DiGraph
from collections import deque, defaultdict


def load_code_graph(graph_info):
    cdg: DiGraph = nx.DiGraph()
    for s, t in zip(graph_info['start_index'], graph_info['end_index']):
        cdg.add_edge(s, t)
    if 'weights' in graph_info and len(graph_info['weights']) > 0:
        if len(graph_info['weights']) == len(graph_info['start_index']):
            for s, t, w in zip(graph_info['start_index'], graph_info['end_index'], graph_info['weights']):
                cdg.edges[s, t]['weight'] = w

    node_attrs = dict({})
    for node in cdg.nodes:
        node_attr = {}
        if str(node) in graph_info['stmt_content']:
            node_attr['stmt'] = graph_info['stmt_content'][str(node)]
        else:
            node_attr['stmt'] = None
        if str(node) in graph_info['stmt_pos']:  # can't use 'pos' cause introducing inner bugs
            node_attr['_pos'] = graph_info['stmt_pos'][str(node)]
        else:
            node_attr['_pos'] = -1
        node_attrs[node] = node_attr
    nx.set_node_attributes(cdg, node_attrs)
    return cdg


def find_control_dependencies(cdg: DiGraph, root: Tuple[int, str], missing_lines: List[Tuple[int, str]]) -> List[
    Tuple[int, int]]:
    """
    Find control dependencies for the instructions of the line in the given CDG
    :param cdg:
    :param root
    :param missing_lines
    :return: list([]). ordered increasingly. -1 removed
    """

    # 1. find all stmts in the line. Be aware that 'throw' may not in cdg
    root_stmts = set({})
    block_stmts = set({})
    for missing_line in missing_lines:
        logging.debug(missing_line)
    for node in cdg.nodes:
        if cdg.nodes[node]['_pos'] == root[0]:
            root_stmts.add(node)
        for missing_line in missing_lines:
            if cdg.nodes[node]['_pos'] == missing_line[0]:
                block_stmts.add(node)

    # 2. find the real root is everything is rooted at 'switch'
    real_root_stmts = {stmt for stmt in root_stmts}
    assert len(real_root_stmts) != 0
    if root[1].strip().startswith("switch"):  # 'switch' is disgusting
        # find the lowest parent outside of block stmts
        # It is likely that 'case' stmt has no corresponding expression in middle representation
        for stmt in block_stmts:
            for in_edge in cdg.in_edges(stmt):
                in_node = in_edge[0]
                if in_node in real_root_stmts or in_node in block_stmts:
                    continue
                if cdg.nodes[in_node]['_pos'] == cdg.nodes[real_root_stmts.__iter__().__next__()]['_pos']:
                    real_root_stmts.add(in_node)
                elif cdg.nodes[in_node]['_pos'] > cdg.nodes[real_root_stmts.__iter__().__next__()]['_pos']:
                    real_root_stmts = {in_node}
    assert len(real_root_stmts) != 0

    # 2. backward BFS
    visited = set({})
    queue = deque([])
    dep = set({})
    # 2.1 init these data structures
    for stmt in real_root_stmts:
        visited.add(stmt)
        queue.append(stmt)
    # 2.2 BFS
    while len(queue) > 0:
        head_node = queue.popleft()
        for in_edge in cdg.in_edges(head_node):
            in_node = in_edge[0]
            if in_node not in visited:
                visited.add(in_node)
                queue.append(in_node)
            dep.add((in_node, cdg.edges[in_edge]['weight']))
    # 2.3 decide the dependency between entrance and missing lines
    enter_condition = defaultdict(int)
    for root_node in real_root_stmts:
        for out_edge in cdg.out_edges(root_node):
            out_node = out_edge[1]
            if out_node in block_stmts:
                # print(cdg.nodes[out_node]['_pos'])
                enter_condition[cdg.edges[out_edge]['weight']] += 1
    assert len(enter_condition) > 0
    logging.info(enter_condition)
    for root_node in real_root_stmts:
        if len(enter_condition) == 1:
            dep.add((root_node, enter_condition.keys().__iter__().__next__()))
        else:
            dep.add((root_node, max(enter_condition, key=enter_condition.get)))

    # 2.3 map stmt to line_no
    control_dependencies = set([(cdg.nodes[node[0]]['_pos'], node[1])
                                for node in dep if cdg.nodes[node[0]]['_pos'] >= 0])
    control_dependencies = sorted(list(control_dependencies), key=lambda x: x[0])
    return control_dependencies
