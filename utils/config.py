import configparser
import inspect
import os

# get the file local path
frame_info = inspect.getframeinfo(inspect.currentframe())
file_path = frame_info.filename  # the abs file path of this `config.py`

# Use configparser.ConfigParser() to read config.ini file.
config = configparser.ConfigParser()
project_root = os.path.abspath(os.path.dirname(os.path.dirname(file_path)))  # abs path
config_path = os.path.join(project_root, "config.ini")
assert os.path.exists(config_path)
config.read(config_path)


def transform_path(path):
    """
    Transform the rel path to abs path if the provided path is not absolute
    :param path:
    :return:
    """
    if path.startswith("/"):  # absolute path. No need to transform
        return path
    paths = path.split(":")
    for idx in range(len(paths)):
        paths[idx] = os.path.normpath(os.path.join(project_root, paths[idx]))
    return ':'.join(paths)


TIMEOUT = eval(config.get("DEFAULT", "TIMEOUT"))

TEMPLATE_NO_DEPS = config.get("DEFAULT", "PROMPT_TEMPLATE_NO_DEPS")
TEMPLATE_WITH_DEPS = config.get("DEFAULT", "PROMPT_TEMPLATE_DEPS")
TEMPLATE_ERROR = config.get("DEFAULT", "PROMPT_TEMPLATE_ERROR")

LANGUAGE = config.get("DEFAULT", "LANGUAGE")
GRAMMAR_FILE = transform_path(config.get("DEFAULT", "GRAMMAR_FILE"))
COBERTURA_DIR = transform_path(config.get("DEFAULT", "COBERTURA_DIR"))
JUNIT_JAR = transform_path(config.get("DEFAULT", "JUNIT_JAR"))
MOCKITO_JAR = transform_path(config.get("DEFAULT", "MOCKITO_JAR"))
LOG4J_JAR = transform_path(config.get("DEFAULT", "LOG4J_JAR"))
JACOCO_AGENT = transform_path(config.get("DEFAULT", "JACOCO_AGENT"))
JACOCO_CLI = transform_path(config.get("DEFAULT", "JACOCO_CLI"))
FORMATTER_PATH = transform_path(config.get("DEFAULT", "FORMATTER"))
REPORT_FORMAT = config.get("DEFAULT", "REPORT_FORMAT")

playground_dir = transform_path(config.get("DEFAULT", "playground"))

api_keys = eval(config.get("openai", "api_keys"))
model = config.get("openai", "model")
model_url = config.get("openai", "model_url")
temperature = eval(config.get("openai", "temperature"))
top_p = eval(config.get("openai", "top_p"))
frequency_penalty = eval(config.get("openai", "frequency_penalty"))
presence_penalty = eval(config.get("openai", "presence_penalty"))

mongo_url = config.get("mongo", "mongo_url")
mongo_port = eval(config.get("mongo", "mongo_port"))
mongo_user = config.get("mongo", "mongo_user")
mongo_pwd = config.get("mongo", "mongo_pwd")
