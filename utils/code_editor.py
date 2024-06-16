import logging
import re
from copy import deepcopy
from typing import Optional, List

from tree_sitter import Language, Parser, Tree, Node
import tree_sitter_java as tsjava
from utils.config import GRAMMAR_FILE, LANGUAGE


def add_import(code):
    lines = code.strip().split('\n')
    package_idx = -1
    for idx, line in enumerate(lines):
        if line.startswith('package'):
            package_idx = idx
            break
    if package_idx == -1:
        return code

    added_imports = list(['import static org.mockito.Mockito.*;'])
    if 'import org.mockito.MockedStatic;' not in code:
        added_imports.append('import org.mockito.MockedStatic;')
    if 'import org.mockito.Mockito;' not in code:
        added_imports.append('import org.mockito.Mockito;')
    lines = lines[:package_idx+1] + added_imports + lines[package_idx+1:]
    return '\n'.join(lines)


def match_from_span(node, blob: str) -> str:
    """
    Extract the source code associated with a node of the tree
    """
    line_start = node.start_point[0]
    line_end = node.end_point[0]
    char_start = node.start_point[1]
    char_end = node.end_point[1]
    lines = blob.split('\n')
    if line_start != line_end:
        return '\n'.join(
            [lines[line_start][char_start:]] + lines[line_start + 1:line_end] + [lines[line_end][:char_end]])
    else:
        return lines[line_start][char_start:char_end]


def tuple_to_index(start_pos, end_pos, blob):
    """
    transform 2-d pos to 1-d pos. [line_start_pos, line_end_pos)
    :param start_pos:
    :param end_pos:
    :param blob:
    :return:
    """
    lines = blob.split('\n')
    for idx in range(len(lines) - 1):
        lines[idx] += '\n'
    line_start_pos = sum([len(lines[idx]) for idx in range(start_pos[0])]) + start_pos[1]
    line_end_pos = sum([len(lines[idx]) for idx in range(end_pos[0])]) + end_pos[1]
    return line_start_pos, line_end_pos


def find_main_cls(tree: Tree, code: str, logger=None) -> Optional[Node]:
    """
    Find the main class of the tree
    :param tree:
    :param code:
    :param logger:
    :return:
    """
    classes = (node for node in tree.root_node.children if node.type == 'class_declaration')
    main_cls = None
    for cls in classes:
        # find the modifiers
        for child in cls.children:
            if child.type == 'modifiers' and 'public' in match_from_span(child, code):
                main_cls = cls
                break
    if main_cls is None:
        if logger is not None:
            logger.warning(f"No public class found")
        return None
    else:
        return main_cls


def remove_assertion(source_code: str) -> str:
    """
    remove assertion statements from the given source code
    :param source_code:
    :return: the source code with assertion statements removed
    """
    assertion_keywords = ['assertEquals', 'assertNotEquals', 'assertSame', 'assertNotSame',
                          'assertTrue', 'assertFalse', 'assertArrayEquals', 'assertNotNull',
                          'assertNull', 'assertThat']
    lines = source_code.strip().split("\n")
    for idx, line in enumerate(lines):
        for assertion_keyword in assertion_keywords:
            if assertion_keyword in line:
                new_line = line.lstrip()
                lines[idx] = line[:len(line) - len(new_line)] + "// " + new_line
                break
    return "\n".join(lines)


class CodeEditor:
    def __init__(self):
        self.parser = Parser()
        self.JAVA_LANGUAGE = Language(tsjava.language(), "java")
        self.parser.set_language(self.JAVA_LANGUAGE)
        self.logger = logging.getLogger()

    def change_main_cls_name(self, content: str, public_cls_name: str) -> Optional[str]:
        """
        Split the generated test cases into separate files. This method returns None when
        1. the public class is failed to find
        2. The identifier of the public class is failed to find
        :param public_cls_name:
        :param content:
        :return:
        """
        # 0. check whether the cls name is valid
        match = re.match(r"[a-zA-Z\$_][a-zA-Z0-9\$_]+", public_cls_name)
        if match is None:
            self.logger.warning(f"the cls name to be changed is invalid: {public_cls_name}. code unchanged")
            return None

        bytes_content = bytes(content, "utf8")
        tree = self.parser.parse(bytes_content)
        # 1. find the public class and edit its name
        main_cls = find_main_cls(tree, content, self.logger)
        if main_cls is None:
            return None

        # 2. modify the main class name if not equal with public_cls_name
        identifier_node = [child for child in main_cls.children if child.type == 'identifier']
        if len(identifier_node) == 0:
            return None
        else:
            identifier_node = identifier_node[0]
        class_identifier = match_from_span(identifier_node, content)
        if class_identifier != public_cls_name:
            bytes_content = (bytes_content[:identifier_node.start_byte] + bytes(public_cls_name, 'utf8') +
                             bytes_content[identifier_node.end_byte:])

        return bytes_content.decode('utf8')

    def split_test_cases(self, content: str, cls_name) -> Optional[List[str]]:
        """
        Given a CU for unit test. Split each test method into several different CU
        The method returns None when:
        1. The public class is failed to find
        2. The class body is failed to find
        :param content:
        :param cls_name: the name of class-to-test
        :return:
        """
        bytes_content = bytes(content, "utf8")
        tree = self.parser.parse(bytes_content)
        # 1. find the public class and edit its name
        main_cls = find_main_cls(tree, content, self.logger)
        if main_cls is None:
            # 1.1 check pattern
            if f"class {cls_name}_Test" not in content:
                return None
            # 1.2 manually modify
            content = content.replace(f"class {cls_name}_Test", f"public class {cls_name}_Test")
            bytes_content = bytes(content, "utf8")
            tree = self.parser.parse(bytes_content)
            main_cls = find_main_cls(tree, content, self.logger)
            # 1.3 check again
            if main_cls is None:
                return None

        # 2. find all classes
        class_body = main_cls.child_by_field_name('body')
        if class_body is None:
            self.logger.warning(f"Find no class body")
            return None
        methods = list([])
        for node in class_body.children:
            # print(node.type)
            if node.type == 'method_declaration':
                methods.append(node)

        # 3. find all tests
        method_of_testing = list([])
        for method in methods:
            for method_child in method.children:
                if method_child.type == 'modifiers':
                    method_modifiers = match_from_span(method_child, content)
                    if '@Test' in method_modifiers:
                        method_of_testing.append(method)

        # 4. slice the tests
        if len(method_of_testing) == 0:
            self.logger.warning(f"No tests found!")
            return [content]
        else:
            refactored_code = []
            method_of_testing = sorted(method_of_testing, key=lambda x: x.start_byte)
            for method_idx in range(len(method_of_testing)):
                bias = 0
                new_bytes_content = deepcopy(bytes_content)
                for method_delete_idx in range(len(method_of_testing)):
                    if method_delete_idx == method_idx:
                        continue
                    else:
                        start_idx = method_of_testing[method_delete_idx].start_byte - bias
                        end_idx = method_of_testing[method_delete_idx].end_byte - bias
                        new_bytes_content = new_bytes_content[:start_idx] + new_bytes_content[end_idx:]
                        bias += end_idx - start_idx
                refactored_code.append(new_bytes_content.decode('utf8'))
            return refactored_code
