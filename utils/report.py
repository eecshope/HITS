import logging
import os
import re
import subprocess
from typing import Optional, List, Dict, Tuple

from bs4 import BeautifulSoup


def sig_split(signature):
    """
    given a signature: xxxx(aaa, bbb, cccc), split it into xxxx, aaa, bbb, cccc
    """
    signature = signature.strip()
    # first, find base name and param group
    first_split = re.match(r"([^()]+)\((.*)\)", signature)
    if first_split is None:
        logging.debug(f"Failed to split {signature}")
        return None
    base = first_split.group(1)  # str
    params_list = [item.strip() for item in first_split.group(2).split(',') if item != ""]  # List[str]
    params_list = [item.split('.')[-1] for item in params_list]

    def _remove_too_much_space(_param):
        _param = [_item for _item in _param.split(" ") if _item != ""]
        return " ".join(_param)

    params_list = [_remove_too_much_space(item) for item in params_list]
    return [base] + params_list


def sig_compare(sig_list_a, sig_list_jacoco):
    if len(sig_list_a) != len(sig_list_jacoco):
        return False
    if len(sig_list_a) == 0:  # length guaranteed to be the same
        return True
    if sig_list_a[0] != sig_list_jacoco[0]:
        return False
    for item_a, item_jacoco in zip(sig_list_a[1:], sig_list_jacoco[1:]):
        if item_jacoco == 'Object':
            continue
        elif item_a != item_jacoco:
            return False
    return True


def jacoco_analysis(report_root, package, class_name, signature) -> Optional[Dict[str, str]]:
    """
    Analysis the report root and find the coverage
    :param report_root:
    :param package:
    :param class_name:
    :param signature:
    :return: {"inst_cov": str, "bran_cov": str}
    """
    html_path = os.path.join(report_root, package, f"{class_name}.html")
    with open(html_path, "r") as file:
        soup = BeautifulSoup(file, 'lxml-xml')

    coverage = dict({})
    for tr in soup.find_all(name='tbody')[0].find_all(name='tr', recursive=False):
        tds = tr.contents
        try:
            method_name = tds[0].span.string
        except AttributeError:
            method_name = tds[0].a.string
        instruction_cov = tds[2].string
        branch_cov = tds[4].string
        coverage[method_name] = {"inst_cov": instruction_cov, "bran_cov": branch_cov}

    # wash signature
    def _iter_replace(_str):
        _cnt = 0
        while True:
            _new_str = re.sub(r"<[^<>]*>", "", _str)
            if _new_str == _str:
                return _str
            else:
                _cnt += 1
                _str = _new_str
                if _cnt == 100000:
                    return _str

    simplified_sig = _iter_replace(signature)
    # find match sig
    simplified_sig = sig_split(simplified_sig)
    match_jacoco_key = None
    if simplified_sig is None:
        logging.error(f"Failed to parse original signature: {signature}")
        return None
    for key in coverage:
        splited_key = sig_split(key)
        if splited_key is None:
            continue
        if sig_compare(simplified_sig, splited_key):
            match_jacoco_key = key
            break

    if len(coverage) == 0:
        logging.error(f"Failed to find any content in {html_path}")
        return None
    elif match_jacoco_key is None:
        logging.error(f"Failed to find cov information for {signature}. Simplified: {simplified_sig}")
        return None
    else:
        return coverage[match_jacoco_key]


def jacoco_missing_lines(report_root, package, class_name) -> Tuple[List[Tuple[int, str]], List[Tuple[int, str]]]:
    html_path = os.path.join(report_root, package, f"{class_name}.java.html")
    with open(html_path, "r") as file:
        soup = BeautifulSoup(file, 'lxml-xml')

    def get_id(_span):
        return int(_span['id'][1:])  # since the 'id' has format 'L{id}', e.g., 'L15', means line 15

    def _case_filter(_str: str):
        return re.match(r"case .*:", _str.strip()) is not None

    missing_lines = [(get_id(_span), _span.string)
                     for _span in soup.find_all("span", class_=re.compile(r"nc(.)*"))]
    branch_lines = [(get_id(_span), _span.string)
                    for _span in soup.find_all("span", class_=re.compile(r"pc b[np]c"))]
    # missing_cases = [get_id(_span) for _span in soup.find_all("span",
    #                                                           class_=re.compile(r"pc b[np]c"),
    #                                                           string=_case_filter)]
    # e.g. for missing cases: case 10: System.out.println("10"); This line will be yellow

    return missing_lines, branch_lines
