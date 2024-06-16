import copy
import os
from typing import Dict

import jinja2
import logging

import tiktoken

from utils.post_process import extract_code


def generate_code(chatter, user_prompt, system_prompt, init_temperature, cls_name, prev_code=None):
    """
    Generate code with the given chatter, user_prompt, system_prompt and init temperature.
    cls_name is for validate the generation.
    The generation has 6 chances. After 6 chances, if no valid code get, runtime error raises
    """
    extracted_code = None
    result = None
    original_user_prompt = user_prompt
    for generate_trial in range(6):
        if generate_trial == 0:
            temperature = init_temperature
        elif init_temperature < 0.2:
            temperature = 0.2
        else:
            temperature = init_temperature
        if generate_trial > 0:
            temperature += 0.1 * (generate_trial - 1)

        r = chatter.generate(user_prompt, system_prompt, temperature=temperature)
        if r[1] is not None:
            result = r[1][0]
        else:
            result = "a;dfkjasd;fjkla"
        has_code, extracted_code, has_syntactic_error = extract_code(result)
        if has_code and not has_syntactic_error and cls_name in extracted_code:
            if prev_code is not None and prev_code == extracted_code:
                extracted_code = None
                error_message = "In previous round of generation, you output is the same as the code to fix. Fix it!"
                user_prompt = original_user_prompt + '\n' + error_message
            else:
                break
        else:
            extracted_code = None
            error_message = ("In previous generation, found syntax error! The brackets must be CLOSED! "
                             "The brackets must be BALANCED!")
            if has_syntactic_error:
                user_prompt = original_user_prompt + '\n' + error_message

    if extracted_code is None:
        raise RuntimeError(f"Failed to generate good code.")

    return extracted_code, result


class BasicProcedure:
    def __init__(self, prompt_root, system_template_file_name, user_template_file_name, procedure_name):
        self.prompt_root = prompt_root
        self.user_template_name = user_template_file_name
        self.system_template_file_name = system_template_file_name
        assert os.path.exists(self.prompt_root)
        assert os.path.exists(os.path.join(self.prompt_root, self.user_template_name))

        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader(prompt_root),
                                      trim_blocks=True,
                                      lstrip_blocks=True)
        self.generate_template = self.env.get_template(self.user_template_name)
        self.system_template = self.env.get_template(self.system_template_file_name)

        self.logger = logging.getLogger(procedure_name)
        self.logger.info(f"{procedure_name} generator started. "
                         f"Template loaded from {os.path.join(prompt_root, user_template_file_name)}")

        self.enc = tiktoken.get_encoding("cl100k_base")
        self.encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

    def count_tokens(self, strings):
        tokens = self.encoding.encode(strings)
        cnt = len(tokens)
        return cnt