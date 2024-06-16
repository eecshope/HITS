import glob
import logging
import subprocess

from utils.config import *


class BasicRunner:

    def __init__(self, target_path):
        """
        /data/share/TestGPT_ASE/result/scope_test%20230414210243%d3_1/ (all test)
        /data/share/TestGPT_ASE/result/scope_test%20230414210243%d3_1/1460%lang_1_f%ToStringBuilder%append%d3/5 (single test)
        :param target_path: target project path
        :param output_path: dir of all output resources. Used only in test all
        """
        self.target_path = target_path

        # Preprocess
        self.dependencies = self.make_dependency()  # paths of dependent jars of the project-under-test: 'a.jar:b.jar'
        self.build_dir_name = "target/classes"
        self.build_dir = self.process_single_repo()  # {target_dir}/target/classes

        self.logger = logging.getLogger('slice_runner')

    def process_single_repo(self):
        """
        Return the all build directories of target repository
        """
        if self.has_submodule(self.target_path):
            modules = self.get_submodule(self.target_path)
            postfixed_modules = [f'{self.target_path}/{module}/{self.build_dir_name}' for module in modules]
            build_dir = ':'.join(postfixed_modules)
        else:
            build_dir = os.path.join(self.target_path, self.build_dir_name)
        return build_dir

    @staticmethod
    def get_package(test_file):
        with open(test_file, "r") as f:
            first_line = f.readline()

        package = first_line.strip().replace("package ", "").replace(";", "")
        return package

    @staticmethod
    def is_module(project_path):
        """
        If the path has a pom.xml file and target/classes compiled, a module.
        """
        if not os.path.isdir(project_path):
            return False
        if 'pom.xml' in os.listdir(project_path) and 'target' in os.listdir(project_path):
            return True
        return False

    def get_submodule(self, project_path):
        """
        Get all modules in given project.
        :return: module list
        """
        return [d for d in os.listdir(project_path) if self.is_module(os.path.join(project_path, d))]

    def has_submodule(self, project_path):
        """
        Is a project composed by submodules, e.g., gson
        """
        for dir in os.listdir(project_path):
            if self.is_module(os.path.join(project_path, dir)):
                return True
        return False

    @staticmethod
    def export_classpath(classpath_file, classpath):
        with open(classpath_file, 'w') as f:
            classpath = "-cp " + classpath
            f.write(classpath)
        return

    def get_full_name(self, test_file):
        package = self.get_package(test_file)
        test_case = os.path.splitext(os.path.basename(test_file))[0]
        if package != '':
            return f"{package}.{test_case}"
        else:
            return test_case

    def make_dependency(self):
        """
        Generate runtime dependencies of a given project
        """
        mvn_dependency_dir = 'target/dependency'
        deps = []
        if not self.has_made():
            # Run mvn command to generate dependencies
            # print("Making dependency for project", self.target_path)
            subprocess.run(
                f"mvn dependency:copy-dependencies -DoutputDirectory={mvn_dependency_dir} -f {self.target_path}/pom.xml",
                shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(f"mvn install -DskipTests -f {self.target_path}/pom.xml", shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        dep_jars = glob.glob(self.target_path + "/target/dependency/**/*.jar", recursive=True)
        deps.extend(dep_jars)
        deps = list(set(deps))
        return ':'.join(deps)

    def has_made(self):
        """
        If the project has made before
        """
        for dirpath, dirnames, filenames in os.walk(self.target_path):
            if 'pom.xml' in filenames and 'target' in dirnames:
                target = os.path.join(dirpath, 'target')
                if 'dependency' in os.listdir(target):
                    return True
        return False
