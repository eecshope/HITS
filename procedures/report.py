import logging
import os.path
import re
import subprocess
import traceback
from typing import Optional, Dict

from pymongo.collection import Collection

from utils import test_runner
from utils.report import jacoco_analysis


def single_method_report(method_experiment_root, collection: Collection, put_path, jacoco_cli_path,
                         build_dir="target/classes", src_dir="src/main/java"):
    """
    Report the coverage data of a
    :param method_experiment_root:
    :param collection
    :param put_path: root dir for the target PUT
    :param jacoco_cli_path:
    :param build_dir: default build dir suffix. Generally, for each module, find classes in {module}/{build_dir}
    :param src_dir: default src dir suffix.
    :return:
    """
    assert os.path.exists(jacoco_cli_path)
    assert os.path.exists(method_experiment_root)
    assert os.path.exists(os.path.join(method_experiment_root, "fixing"))
    fixing_root = os.path.join(method_experiment_root, "fixing")
    output_root = os.path.join(method_experiment_root, 'full_report')
    os.makedirs(output_root, exist_ok=True)
    slices = list([])
    for _dir in os.listdir(fixing_root):
        if os.path.isdir(os.path.join(fixing_root, _dir)):
            slices.append(os.path.join(fixing_root, _dir))

    # aggregate the report
    exec_paths = list([])
    for _slice in slices:
        trials = [_dir for _dir in os.listdir(_slice) if re.match(r"\d+", _dir)]
        trials = sorted(trials, reverse=True)
        for trial in trials:
            exec_path = os.path.join(_slice, str(trial), "runtemp", "jacoco.exec")
            if not os.path.exists(exec_path):
                exec_path = os.path.join(_slice, str(trial), "cov_check_dir", "jacoco.exec")  # old version
            runtime_error = os.path.join(_slice, str(trial), "temp", "runtime_error.txt")
            compile_error = os.path.join(_slice, str(trial), "temp", "compile_error.txt")
            if os.path.exists(exec_path) and not os.path.exists(runtime_error) and not os.path.exists(compile_error):
                exec_paths.append(exec_path)
                break
    if len(exec_paths) == 0:
        logging.warning(f"Found no exec file in experiment {method_experiment_root}")
        return None

    # get target class paths
    module_poms = test_runner.parse_root_pom(put_path)
    target_class_paths = [os.path.join(os.path.dirname(module_pom), build_dir) for module_pom in module_poms]
    target_class_paths = [path for path in target_class_paths if os.path.exists(path)]
    if len(target_class_paths) == 0:
        logging.error(f"Found no target dirs!")

    # get located module
    info = collection.find_one({"table_name": "info"})
    assert info is not None
    class_path = os.path.join(os.path.abspath(put_path), info['class_path'])
    target_src_root = None
    for pom_path in module_poms:
        module_src_root = os.path.join(os.path.abspath(os.path.dirname(pom_path)), src_dir)
        if class_path.startswith(module_src_root):
            target_src_root = module_src_root
    if target_src_root is None:
        logging.warning(f"Found no target src root for {method_experiment_root}")

    report_order = ["java", "-jar", jacoco_cli_path, "report"] + exec_paths
    for path in target_class_paths:
        report_order += ['--classfiles', path]
    report_order += ['--html', output_root]
    if target_src_root is not None:
        report_order += ['--sourcefiles', target_src_root]
    report = subprocess.run(report_order, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return report.stderr.decode().strip() == ""


def single_method_analyse(log_dir, collection: Collection) -> Optional[Dict]:
    # analyse the report
    assert os.path.exists(log_dir)
    assert os.path.exists(os.path.join(log_dir, "full_report"))
    raw_info = collection.find_one({"table_name": "raw_data"})
    assert raw_info is not None

    signature = raw_info['parameters']
    package = raw_info['package'].replace("package ", "").replace(";", "")
    class_name = raw_info['class_name']

    try:
        coverage_result = jacoco_analysis(os.path.join(log_dir, "full_report"),
                                          package,
                                          class_name,
                                          signature)
    except FileNotFoundError as e:
        traceback.print_exception(e)
        coverage_result = None

    if coverage_result is None:
        return {".".join([package, class_name, signature]): {'inst_cov': '0%', 'bran_cov': '0%'}}
    else:
        return {".".join([package, class_name, signature]): coverage_result}
