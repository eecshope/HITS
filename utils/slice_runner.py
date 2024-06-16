import logging
import subprocess

from utils.basic_runner import BasicRunner
from utils.config import *


class SliceRunner(BasicRunner):

    def __init__(self, target_path, output_path, slicer_jar_path):
        """
        :param tool: coverage tool (Only support cobertura or jacoco)
        :param test_path: test cases directory path e.g.:
        /data/share/TestGPT_ASE/result/scope_test%20230414210243%d3_1/ (all test)
        /data/share/TestGPT_ASE/result/scope_test%20230414210243%d3_1/1460%lang_1_f%ToStringBuilder%append%d3/5 (single test)
        :param target_path: target project path
        :param output_path: dir of all output resources. Used only in test all
        """
        super(SliceRunner, self).__init__(target_path)
        self.output_path = output_path
        self.slicer_jar_path = slicer_jar_path
        assert slicer_jar_path.endswith(".jar")
        assert os.path.exists(slicer_jar_path)

        if not os.path.exists(output_path):
            os.makedirs(output_path)

        self.logger = logging.getLogger('slice_runner')

    def start_single_slice(self, target_src_file, criterion_line):
        class_path = f"{self.slicer_jar_path}:{self.dependencies}:{self.build_dir}:."
        # cmd = f"java -cp {class_path} -jar {self.slicer_jar_path} -f {target_src_file} -l {criterion_line}"
        cmd = f"java -jar {self.slicer_jar_path} "
        try:
            result = subprocess.run(cmd, timeout=TIMEOUT,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                self.logger.error(result.stderr)
                return False
        except subprocess.TimeoutExpired:
            # print(Fore.RED + "TIME OUT!", Style.RESET_ALL)
            self.logger.error("Time Out!")
            return False
