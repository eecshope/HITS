import json
import logging
import os
from typing import Optional, List, Dict

from pymongo.collection import Collection

from generator.open_generator import OpenGenerator
from procedures.basic_procedure import BasicProcedure
from utils.code_editor import CodeEditor
from utils.post_process import extract_code


class InitialCodeGenerator(BasicProcedure):
    def __init__(self, prompt_root, system_template_file_name, init_code_generate_template_file_name):
        super(InitialCodeGenerator, self).__init__(prompt_root, system_template_file_name,
                                                   init_code_generate_template_file_name, "init_code_generator")
        self.code_editor = CodeEditor()

    def generate_code(self, direction_3, step_id, chatter, log_dir, init_temp=0.0, capacity=-1):
        """
        :param direction_3: the dict containing all info filling the template
        :param step_id: str, an int if normal slice or 'fixing_x' for fixing. x is number, e.g., fixing_1
        :param chatter
        :param log_dir: dir to save the log
        :param init_temp
        :param capacity: how much capacity for  this round of generation. if -1, no limit.
        :return:
        """
        # cls_name = "_".join([direction_3['simple_class_name'], direction_3['simple_method_name'], str(i), 'Test'])
        logger_name = log_dir.replace('.', '/') + f".{step_id}"
        logger = logging.getLogger(name=logger_name)
        logger.propagate = False
        logger.handlers = []
        logger.addHandler(logging.FileHandler(os.path.join(log_dir, f'log_{step_id}.txt')))
        logger.setLevel(logging.INFO)
        # logger.addHandler(logging.StreamHandler())

        response = ""
        tests_by_condition = list([])

        for generate_trial in range(5):
            temperature = init_temp if generate_trial == 0 else 0.5
            response_0 = chatter.generate(self.generate_template.render(direction_3),
                                          self.system_template.render(),
                                          temperature=temperature)
            if response_0[0] != 200:
                logger.error(f"Error when communicate with GPT. Error code: {response_0[0]}")
                continue
            else:
                response = response_0[1][0]
            has_code, extracted_code, has_syntactic_error = extract_code(response)
            # print(cls_name)
            # print(extracted_code)
            if has_code and not has_syntactic_error:
                tests_by_condition = self.code_editor.split_test_cases(extracted_code, direction_3['simple_class_name'])
                if tests_by_condition is None:
                    tests_by_condition = []
                    logger.warning(f"For task {log_dir},"
                                   f"solution step {step_id}, in trial {generate_trial}, no valid public class found")
                else:
                    break
            else:
                if not has_code:
                    logger.warning(f"For task {log_dir},"
                                   f"solution step {step_id}, in trial {generate_trial}, no code found in response")
                if has_syntactic_error:
                    logger.warning(f"For task {log_dir},"
                                   f"solution step {step_id}, in trial {generate_trial}, syntactic error")
                logger.info(f"The response is \n{response}")
                tests_by_condition = list([])

        if step_id is int:
            step_id = str(step_id)

        unit_tests = list([])
        has_output = False
        if capacity >= 0:
            tests_by_condition = tests_by_condition[:capacity]
        for condition_idx, test_by_condition in enumerate(tests_by_condition):
            has_output = True
            cls_name = "_".join([direction_3['simple_class_name'], step_id, str(condition_idx), "Test"])
            output_content = self.code_editor.change_main_cls_name(test_by_condition, cls_name)
            if output_content is None:
                output_content = test_by_condition
            with open(os.path.join(log_dir, f"{cls_name}.java"), "w",
                      encoding='utf-8') as file:
                file.write(output_content)
            with open(os.path.join(log_dir, f"{cls_name}.prompt.txt"), "w",
                      encoding='utf-8') as file:
                file.write(self.generate_template.render(direction_3))
            if 'step_id' in direction_3:
                with open(os.path.join(log_dir, f"{cls_name}.condition.txt"), 'w', encoding='utf-8') as file:
                    file.write(direction_3['steps'][direction_3['step_id']]['desp'])
            unit_tests.append(output_content)

        if has_output:
            with open(os.path.join(log_dir, f"{direction_3['simple_class_name']}_{step_id}.response.txt"), "w",
                      encoding='utf-8') as file:
                file.write(response)
            self.logger.info(f"For solution step {step_id} in working dir {log_dir}, task success")
        else:
            logger.error(f"For solution step {step_id}, failed to generate any code")
            self.logger.error(f"For solution step {step_id}, failed to generate any code")
        return unit_tests

    def work(self, collection: Collection, chatter: OpenGenerator, log_dir: str, fix_num=-1, fixing=False) \
            -> Optional[List[str]]:
        """
        generate initial code. if fixing, it is a fixing generate for missing lines. else, normal generation
        :param log_dir:
        :param collection:
        :param chatter:
        :param fix_num: if set, the step info will be discarded. Works only when fixing=False
        :param fixing:
        :return:
        """

        direction_3: Dict = collection.find_one({"table_name": "direction_3"})
        direction_1: Dict = collection.find_one({"table_name": "direction_1"})
        addon_info: Dict = collection.find_one({"table_name": "add_info"})
        info: Dict = collection.find_one({"table_name": "info"})
        assert direction_3 is not None
        assert direction_1 is not None
        assert addon_info is not None
        assert info is not None

        # count slices
        assert 'steps' in addon_info
        if type(addon_info) is not dict:
            self.logger.error(f"Failed to fine 'steps' in addon_info for {collection}")
            return None
        self.logger.info(f"Count {len(addon_info['steps'])} slices")

        direction_3.update(addon_info)
        direction_3['simple_class_name'] = direction_1['class_name']
        direction_3['simple_method_name'] = direction_1['focal_method']
        unit_tests = []

        if not fixing:
            direction_3['missing_lines'] = False
            os.makedirs(os.path.join(log_dir, "steps"), exist_ok=True)

            if fix_num < 0:
                for i in range(len(addon_info['steps'])):
                    self.logger.info(f"Generating init unit test for slice {i + 1}")
                    direction_3['step_id'] = i
                    unit_tests += self.generate_code(direction_3, str(i), chatter, os.path.join(log_dir, "steps"))
            else:
                assert fix_num > 0
                _round = 0
                while len(unit_tests) < fix_num:
                    self.logger.info(f"Generating init unit test for slice {_round + 1}")
                    unit_tests += self.generate_code(direction_3, str(_round), chatter, os.path.join(log_dir, "steps"),
                                                     init_temp=0.5, capacity=fix_num - len(unit_tests))
                    _round += 1
                unit_tests = unit_tests[:fix_num]

        else:
            direction_3['has_missing_lines'] = True
            # load slice info
            slice_info_path = os.path.join(log_dir, "slice_fixing", "slice_result.jsonl")
            assert os.path.exists(slice_info_path)
            slices_to_fix = list([])
            with open(slice_info_path, 'r') as file:
                slices_to_fix += [json.loads(line) for line in file.read().strip().split("\n")]
            method_lines = info['method_graphs'][0]['src_lines']

            def _build_line(_line_map, _line_no):
                return f"{_line_no}:{_line_map[str(_line_no)]}" if str(_line_no) in _line_map else ""

            for idx, slice_to_fix in enumerate(slices_to_fix):
                missing_lines = [_build_line(method_lines, idx) for idx in slice_to_fix['missing_lines']]
                condition = _build_line(method_lines, slice_to_fix['slicing_criteria'][0])
                data_slicers = [_build_line(method_lines, idx) for idx in slice_to_fix['sliced_lines']]
                data_dependencies = [_build_line(method_lines, idx) for idx in slice_to_fix['data_def']]
                ctl_dependencies = [_build_line(method_lines, idx[0]) +
                                    f" # The predicate should be {'True' if idx[1]!=0 else 'False'}"
                                    for idx in slice_to_fix['ctl_deps']]
                numbered_fm = [_build_line(method_lines, idx) for idx in method_lines]
                direction_3['missing_lines'] = "\n".join(missing_lines)
                direction_3['condition'] = condition
                direction_3['data_dependencies'] = '\n'.join(data_dependencies)
                direction_3['data_slicers'] = '\n'.join(data_slicers)
                direction_3['ctl_dep'] = '\n'.join(ctl_dependencies)
                direction_3['numbered_fm'] = '\n'.join(numbered_fm)
                self.logger.info(f"Generating fixing unit test for missing clise {idx}")
                unit_tests += self.generate_code(direction_3, f"Fix{idx}", chatter,
                                                 os.path.join(log_dir, "slice_fixing"))

        return unit_tests
