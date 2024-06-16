import json
import logging
import os.path
import re

from pymongo.collection import Collection

from utils.load_code_graph import load_code_graph, find_control_dependencies
from utils.report import jacoco_missing_lines


def parse_missing(method_experiment_root, collection: Collection):
    assert os.path.exists(method_experiment_root)
    # get report root
    if not os.path.exists(os.path.join(method_experiment_root, "full_report")):
        raise ValueError("Report dir not found")
    report_root = os.path.join(method_experiment_root, "full_report")

    # get MUT info
    raw_info = collection.find_one({"table_name": "raw_data"})
    assert raw_info is not None
    package = raw_info['package'].replace("package ", "").replace(";", "")
    class_name = raw_info['class_name']

    # get missing lines
    red_lines, branch_lines = jacoco_missing_lines(report_root, package, class_name)
    # print(red_lines)

    # load stmts in method
    method_info = collection.find_one({"table_name": "info"})
    assert method_info is not None
    stmts_lines = set({})
    for stmt_id in method_info['method_graphs'][0]['stmt_pos']:
        stmts_lines.add(method_info['method_graphs'][0]['stmt_pos'][stmt_id])

    # load call dependency graph
    method_cdg = load_code_graph(method_info['method_graphs'][0])

    # find all patterns: ybbbb ybbbb

    # merge missing_liens (b) and branch_lines (y)
    def _merge_list(_line_a, _line_b, _valid):
        _ptr_a = 0
        _ptr_b = 0
        # _valid = list(range(min(_valid), max(_valid)+1)) don't do that. 'throw' is not in cdg
        _line_a = [_ele for _ele in _line_a if _ele[0] in _valid]
        _line_b = [_ele for _ele in _line_b if _ele[0] in _valid]
        _result = []
        _str = ""
        while _ptr_a < len(_line_a) and _ptr_b < len(_line_b):
            if _line_a[_ptr_a][0] < _line_b[_ptr_b][0]:
                _result.append(_line_a[_ptr_a])
                _str += "a"
                _ptr_a += 1
            else:
                _result.append(_line_b[_ptr_b])
                _str += "b"
                _ptr_b += 1
        if _ptr_a < len(_line_a):
            _result += _line_a[_ptr_a:]
            _str += "a" * (len(_line_a) - _ptr_a)
        if _ptr_b < len(_line_b):
            _result += _line_b[_ptr_b:]
            _str += "b" * (len(_line_b) - _ptr_b)
        return _result, _str
    missing_lines_in_method, raw_pattern = _merge_list(branch_lines, red_lines, stmts_lines)
    splits = [missing_lines_in_method[slice(*result.span())] for result in re.finditer(r"ab+", raw_pattern)]
    logging.warning(raw_pattern)
    logging.warning(f"Found {len(splits)} splits")

    # save the splits
    cls_name = 'L' + method_info['class_name_full'].replace('.', '/')
    json_lines = list([])
    output_dir = os.path.join(method_experiment_root, 'slice_fixing')
    os.makedirs(output_dir, exist_ok=True)
    try:
        for missing_chunk in splits:
            root = missing_chunk[0]
            missing_lines = missing_chunk[1:]
            # check the relationship between missing_lines and root_pos

            ctl_deps = [list(line_no) for line_no in find_control_dependencies(method_cdg, root, missing_lines)
                        if line_no[0] not in red_lines]
            if len(ctl_deps) > 0 and ctl_deps[0] == -1:
                ctl_deps = ctl_deps[1:]

            json_lines.append(json.dumps({"cls_name": cls_name,
                                          "missing_lines": [element[0] for element in missing_lines],
                                          "slicing_criteria": [root[0]],
                                          "ctl_deps": ctl_deps}))
    except AssertionError:
        logging.error(f"Failed to parse {method_experiment_root}")
        return
    with open(os.path.join(output_dir, "missing_slices.jsonl"), "w") as file:
        file.write("\n".join(json_lines))
    return json_lines
