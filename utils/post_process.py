import javalang
import re

from utils.code_editor import add_import


def is_syntactic_correct(code):
    """
    Check if the code is syntactically correct
    :param code:
    :return:
    """
    try:
        javalang.parse.parse(code)
        return True
    except Exception as e:
        return False


def syntactic_check(code):
    """
    Syntactic repair
    :param code:
    :return: has_syntactic_error, code
    """
    if is_syntactic_correct(code):
        return False, code
    else:
        stop_point = [";", "}", "{", " "]  # Stop point
        for idx in range(len(code) - 1, -1, -1):
            if code[idx] in stop_point:
                code = code[:idx + 1]
                break
        left_bracket = code.count("{")
        right_bracket = code.count("}")
        for idx in range(left_bracket - right_bracket):
            code += "}\n"

        if is_syntactic_correct(code):
            return True, code

        matches = list(re.finditer(r"(?<=\})[^\}]+(?=@)", code))
        if matches:
            code = code[:matches[-1].start() + 1]
            left_count = code.count("{")
            right_count = code.count("}")
            for _ in range(left_count - right_count):
                code += "\n}"
        if is_syntactic_correct(code):
            return True, code
        else:
            return True, ""


def clean_line_no(code: str):
    """
    in case the LLM generates code each line starts with a line no
    """
    code = code.strip().split('\n')
    for idx, line in enumerate(code):
        match = re.match(r"\d+:", line)
        if match is not None:
            code[idx] = line[match.span()[1]:]
    return '\n'.join(code)


def extract_code(string):
    """
    Check if the string is valid code and extract it.
    :param string:
    :return: has_code, extracted_code, has_syntactic_error
    """
    # if the string is valid code, return True
    if is_syntactic_correct(string):
        return True, string, False

    has_code = False
    extracted_code = ""
    has_syntactic_error = False

    def _match_check(_pattern, _string):
        # Find all matches in the text
        _has_code = False
        _extracted_code = ""
        _has_syntactic_error = False
        _matches = re.findall(_pattern, _string)
        if _matches:
            # Filter matches to only include ones that contain "@Test"
            _filtered_matches = [_match.strip() for _match in _matches if
                                 "@Test" in _match and "class" in _match and "import" in _match]
            if _filtered_matches:
                for _match in _filtered_matches:
                    _match = clean_line_no(_match)
                    _has_syntactic_error, _extracted_code = syntactic_check(_match)
                    if _extracted_code != "":
                        _has_code = True
                        break
        return _has_code, _extracted_code, _has_syntactic_error

    if '```[java]' in string:
        has_code, extracted_code, has_syntactic_error = _match_check(r"```\[java\]*([\s\S]*?)```", string)

    if not has_code and "```java" in string:
        has_code, extracted_code, has_syntactic_error = _match_check(r"```java*([\s\S]*?)```", string)

    if not has_code and "```Java" in string:
        has_code, extracted_code, has_syntactic_error = _match_check(r"```Java*([\s\S]*?)```", string)

    if not has_code and "```[Java]" in string:
        has_code, extracted_code, has_syntactic_error = _match_check(r"```\[Java\]*([\s\S]*?)```", string)

    if not has_code and '```' in string:
        has_code, extracted_code, has_syntactic_error = _match_check(r"```*([\s\S]*?)```", string)

    if not has_code:
        allowed = ["import", "packages", "", "@"]
        code_lines = string.split("\n")
        start, anchor, end = -1, -1, -1
        allowed_lines = [False for _ in range(len(code_lines))]
        left_brace = {x: 0 for x in range(len(code_lines))}
        right_brace = {x: 0 for x in range(len(code_lines))}
        for i, line in enumerate(code_lines):
            left_brace[i] += line.count("{")
            right_brace[i] += line.count("}")
            striped_line = line.strip()

            for allow_start in allowed:
                if striped_line.startswith(allow_start):
                    allowed_lines[i] = True
                    break

            if re.search(r'public class .*Test', line) and anchor == -1:
                anchor = i

        if anchor != -1:
            start = anchor
            while start:
                if allowed_lines[start]:
                    start -= 1

            end = anchor
            left_sum, right_sum = 0, 0
            while end < len(code_lines):
                left_sum += left_brace[end]
                right_sum += right_brace[end]
                if left_sum == right_sum and left_sum >= 1 and right_sum >= 1:
                    break
                end += 1

            temp_code = "\n".join(code_lines[start:end + 1])
            has_syntactic_error, temp_code = syntactic_check(temp_code)
            if temp_code != "":
                extracted_code = temp_code
                has_code = True

    extracted_code = extracted_code.strip()
    if has_code and not has_syntactic_error:
        extracted_code = add_import(extracted_code)
    return has_code, extracted_code, has_syntactic_error
