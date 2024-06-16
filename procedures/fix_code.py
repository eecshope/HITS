import glob
import os.path
import shutil

from pymongo.collection import Collection

from generator.open_generator import OpenGenerator
from procedures.basic_procedure import BasicProcedure, generate_code
from utils import test_runner
from utils.code_editor import remove_assertion
from utils.config import *
from utils.report import jacoco_analysis


def remove_assertion_retest(step_workspace, put_path) -> bool:
    """
    If the test case's failure is due to assertion error, try to remove that assertion statement and retest
    :param step_workspace: the fir for 'temp' and 'runtemp', the workspace of a unit test CU
    :param put_path, the path of the project-under-test
    :return: bool, indicating the test result
    """
    runtime_error_path = os.path.join(step_workspace, "temp", "runtime_error.txt")
    if os.path.exists(runtime_error_path):
        with open(runtime_error_path, "r") as file:
            runtime_error = file.read()
        if "AssertionFailedError" in runtime_error:  # try to remove assertions
            # load the unit test
            temp_files = os.listdir(os.path.join(step_workspace, "temp").__str__())
            test_file_path = None
            for file_name in temp_files:
                if file_name.endswith(".java"):
                    test_file_path = os.path.join(step_workspace, "temp", file_name)
            if test_file_path is None:
                return False
            else:
                with open(test_file_path, "r") as file_handler:
                    failed_test = file_handler.read().strip()

            # remove failed assertion
            assertion_removed_test = remove_assertion(failed_test)
            with open(test_file_path, "w") as java_file:
                java_file.write(assertion_removed_test)

            # restore test env
            shutil.rmtree(os.path.join(step_workspace, "runtemp"))
            os.remove(runtime_error_path)

            # new round of test
            task = test_runner.TestRunner(step_workspace,
                                          put_path,
                                          step_workspace,
                                          "jacoco")
            test_fixed = task.start_single_test()
            return test_fixed
    return False


def coverage_check(slice_work_space, signature, package, class_name):
    """
    structure of slice_work_space
    - slice_work_space
        - runtemp: dir for the test src's .class file
        - temp: dir for test src and execution report
        - cov_check_dir: exists if execution success
    """
    # first check exec record
    assert os.path.exists(os.path.join(slice_work_space, 'runtemp', 'jacoco.exec'))
    if not os.path.exists(os.path.join(slice_work_space, "cov_check_dir")):
        return None

    coverage_result = jacoco_analysis(os.path.join(slice_work_space, "cov_check_dir"),
                                      package,
                                      class_name,
                                      signature)
    return coverage_result


def advanced_run_check(slice_workspace, put_path, signature, package, class_name):
    task = test_runner.TestRunner(slice_workspace,
                                  put_path,
                                  slice_workspace,
                                  "jacoco")
    test_passed = task.start_single_test()
    if not test_passed:
        # remove assertion trial
        test_passed = remove_assertion_retest(slice_workspace, put_path)

    if test_passed:
        coverage_analysis = coverage_check(slice_workspace,
                                           signature, package, class_name)
        if coverage_analysis is None:
            test_passed = False
            with open(os.path.join(slice_workspace, "temp", "run_check_fail.txt"), "w") as file:
                file.write(f"Failed to run check for {signature}. Check details")
        else:
            for key in coverage_analysis:
                if float(coverage_analysis[key].strip("%")) == 0:
                    test_passed = False
                    with open(os.path.join(slice_workspace, "temp", "runtime_error.txt"), "w") as file:
                        file.write(f"Runtime error: {key} is 0%. The test method is not invoked")
                        break
    return test_passed


class TestFixer(BasicProcedure):
    def __init__(self, prompt_root, system_template_file_name, fixer_template_file_name):
        super(TestFixer, self).__init__(prompt_root, system_template_file_name, fixer_template_file_name, "fixer")

    def init_test(self, log_dir, put_path, collection: Collection, fixing=False):
        """
        init test for code generated in the first round
        :param collection:
        :param log_dir:
        :param put_path:
        :param fixing: if this is a following fixing step.
        :return:
        """
        code_dir = "steps" if not fixing else "slice_fixing"
        assert os.path.exists(log_dir)
        assert os.path.exists(os.path.join(log_dir, code_dir))
        os.makedirs(os.path.join(log_dir, "test_cases"), exist_ok=True)
        os.makedirs(os.path.join(log_dir, "temp"), exist_ok=True)
        raw_info = collection.find_one({"table_name": "raw_data"})
        assert raw_info is not None

        test_cases = [os.path.basename(path)
                      for path in glob.glob(os.path.join(log_dir, code_dir, "*.java"), recursive=False)]
        failed_test_cases = []
        for test_case in test_cases:
            target_dir = os.path.join(log_dir, "fixing", test_case[:-len(".java")], "0", "temp")
            if os.path.exists(os.path.dirname(target_dir)):
                self.logger.warning(f"Target dir {os.path.dirname(target_dir)} exists. Skipping...")
                continue
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy(os.path.join(log_dir, code_dir, test_case), target_dir)
            if os.path.exists(os.path.join(log_dir, code_dir, test_case.replace(".java", ".condition.txt"))):
                shutil.copy(os.path.join(log_dir, code_dir, test_case.replace(".java", ".condition.txt")),
                            os.path.dirname(os.path.dirname(target_dir)))
            test_passed = advanced_run_check(os.path.dirname(target_dir), put_path, raw_info['parameters'],
                                             raw_info['package'].replace("package ", "").replace(";", ""),
                                             raw_info['class_name'])
            if not test_passed:
                failed_test_cases.append(test_case)

        if len(failed_test_cases) > 0:
            self.logger.warning(f"{len(failed_test_cases)} / {len(test_cases)} failed")

        failed_test_cases = [t[:-len('.java')] for t in failed_test_cases]
        output_file = os.path.join(log_dir, "fixing", "init_test_failed.txt")
        with open(output_file, "a") as file:
            if os.path.exists(output_file) and os.stat(output_file).st_size > 0:
                file.write('\n')
            file.write("\n".join(failed_test_cases))
        return failed_test_cases

    def single_unitest_fix(self, log_dir, collection: Collection, unitest_failed, put_path,
                           chatter: OpenGenerator) -> bool:
        """
        Fix single unitest in path {method_experiment_root}/fixing/{unitest_failed}
        :param collection:
        :param chatter:
        :param put_path:
        :param log_dir: literal meaning
        :param unitest_failed: see the intro
        :return: whether the unit test is fixed
        """
        unitest_root = os.path.join(log_dir, "fixing", unitest_failed)
        assert os.path.exists(unitest_root)
        existing_trials = [int(trial_id) for trial_id in os.listdir(unitest_root.__str__())
                           if os.path.isdir(os.path.join(unitest_root.__str__(), trial_id))]
        start_trial_to_fix = max(existing_trials)
        start_error = glob.glob(os.path.join(unitest_root.__str__(), str(start_trial_to_fix), "temp", "*error.txt"))
        if len(start_error) == 0:
            return True

        max_trial = 10
        # load method info
        raw_info = raw_data = collection.find_one({"table_name": "raw_data"})
        dir_3 = collection.find_one({"table_name": "direction_3"})
        assert raw_info is not None
        assert dir_3 is not None
        is_not_public = not raw_data['is_public']

        test_fixed = False
        init_temperature = 0.0

        # load the block
        if os.path.exists(os.path.join(unitest_root.__str__(), f"{unitest_failed}.condition.txt")):
            with open(os.path.join(unitest_root.__str__(), f"{unitest_failed}.condition.txt"), "r") as file:
                block = file.read()
        else:
            block = ""

        src_trial = start_trial_to_fix
        for tgt_trial in range(start_trial_to_fix + 1, max_trial + 1):
            src_trial_workspace = os.path.join(unitest_root.__str__(), str(src_trial))
            tgt_trial_workspace = os.path.join(unitest_root.__str__(), str(tgt_trial))

            # load unitest
            with open(os.path.join(src_trial_workspace, "temp", unitest_failed + ".java"), "r") as file:
                unitest_to_fix = file.read().strip()
            # add line numbers
            numbered_unitest_to_fix = '\n'.join([f"{idx+1}: {line}"
                                                 for idx, line in enumerate(unitest_to_fix.split('\n'))])

            # load error file: compile_error, runtime_error has reports. out of time has no report
            compile_error_path = os.path.join(src_trial_workspace, "temp", "compile_error.txt")
            runtime_error_path = os.path.join(os.path.dirname(compile_error_path), "runtime_error.txt")
            run_check_fail = os.path.join(os.path.dirname(compile_error_path), 'run_check_fail.txt')
            if os.path.exists(compile_error_path):
                error_type = "compile_error"
                with open(compile_error_path, "r") as file:
                    error_msg = file.read()
            elif os.path.exists(runtime_error_path):
                error_type = "runtime_error"
                with open(runtime_error_path, "r") as file:
                    error_msg = file.read()
            elif os.path.exists(run_check_fail):
                self.logger.error(f"Run check failed for {log_dir}")
                return False
            else:
                self.logger.error(f"No error found?")
                return False

            error_info = dict([])

            error_info['unit_test'] = numbered_unitest_to_fix
            error_info['error_message'] = '\n'.join([error_type, error_msg])
            error_info['error_type'] = error_type
            error_info['is_not_public'] = is_not_public
            error_info['class_name'] = dir_3['class_name']
            error_info['method_identifier'] = raw_data['method_name']
            error_info['block'] = block
            if 'example' in dir_3:
                error_info['example'] = dir_3['example']

            extracted_code = unitest_to_fix.strip()
            response = "Failed to generate any new code"

            try:
                extracted_code, response = generate_code(chatter, self.generate_template.render(error_info),
                                                         self.system_template.render(dir_3),
                                                         init_temperature=init_temperature, cls_name=unitest_failed,
                                                         prev_code=unitest_to_fix.strip())
            except RuntimeError as e:
                print(e)

            # put down the new generated code
            os.makedirs(os.path.join(tgt_trial_workspace, "temp"), exist_ok=True)
            with (open(os.path.join(tgt_trial_workspace, "temp", unitest_failed + ".java"), "w") as file):
                file.write(extracted_code)
            with (open(os.path.join(tgt_trial_workspace, "temp", "system_prompt.txt"), "w") as file):
                file.write(self.system_template.render(dir_3))
            with (open(os.path.join(tgt_trial_workspace, "temp", "generate_prompt.txt"), "w") as file):
                file.write(self.generate_template.render(error_info))
            with (open(os.path.join(tgt_trial_workspace, "temp", "response.txt"), "w") as file):
                file.write(response)

            # test
            test_fixed = advanced_run_check(tgt_trial_workspace, put_path, raw_info['parameters'],
                                            raw_info['package'].replace("package ", "").replace(";", ""),
                                            raw_info['class_name'])

            if test_fixed:
                break
            # check if the code has changed
            if extracted_code.strip() == unitest_to_fix.strip():
                init_temperature = 0.4
            else:
                init_temperature = 0.0
            src_trial = tgt_trial

        return test_fixed
