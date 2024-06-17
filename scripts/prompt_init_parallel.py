import argparse
import glob
import json
from json import JSONDecodeError

from pymongo import MongoClient
from concurrent.futures import Future
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from generator.openlimit import ChatRateLimiter
from tqdm import tqdm

from procedures import get_code
from utils.config import *
from generator import open_generator

print(f"Please check the working dir {os.getcwd()}. For stability, sys.path will not be modified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_name", required=True)
    parser.add_argument("--fixing", action='store_true')
    parser.add_argument("--wo_slice", action='store_true')
    args = parser.parse_args()
    project_name = args.project_name

    # setup db
    client = MongoClient(mongo_url, mongo_port)
    db = client[project_name]
    print(f"Mongo url: {mongo_url}:{mongo_port}")
    print(f"Playground dir: {os.path.join(playground_dir, project_name)}")
    print(f"is_fixing: {args.fixing}")
    print(f"wo_slice: {args.wo_slice}")
    item = input("\nConfirm to continue? (press y to continue: ")
    if item != 'y':
        print(f"Receive command {item} not y. Stop.")

    # load meta learning
    with open(os.path.join(playground_dir, project_name, "meta.json"), "r") as file:
        meta_info = json.load(file)
    print(f"Counting {len(meta_info['idx_to_method_name'])} methods to test")

    # define thread
    monitor = ChatRateLimiter(10000, 900000, 60)
    if args.wo_slice:
        prompt_root = 'prompts/no_slice'
        method_workspaces_prefix = 'methods_no_slice'
    else:
        prompt_root = 'prompts/no_mock'
        method_workspaces_prefix = 'methods'

    def thread_init_generation(_method_to_test):
        if args.fixing:
            _code_getter = get_code.InitialCodeGenerator(prompt_root,
                                                         "system_gen.jinja2",
                                                         "gen_patch.jinja2")
        else:
            _code_getter = get_code.InitialCodeGenerator(prompt_root,
                                                         "system_gen.jinja2",
                                                         "gen_code.jinja2")
        _chatter = open_generator.OpenGenerator(key=api_keys, request_url=model_url,
            model='gpt-3.5-turbo-0125', monitor=monitor)
        _log_dir = os.path.join(playground_dir, project_name, method_workspaces_prefix,
                                meta_info['method_name_to_idx'][_method_to_test])
        if args.fixing and not os.path.exists(os.path.join(_log_dir.__str__(), 'slice_fixing', 'slice_result.jsonl')):
            return
        try:
            if args.fixing or not args.wo_slice:
                _code_getter.work(db.get_collection(_method_to_test), _chatter, _log_dir.__str__(), fixing=args.fixing)
            else:
                _test_case_cnt = len(glob.glob(os.path.join(playground_dir, project_name, 'methods',
                                                            meta_info['method_name_to_idx'][_method_to_test],
                                                            'steps', "*.java")))
                _code_getter.work(db.get_collection(_method_to_test), _chatter, _log_dir.__str__(),
                                  fix_num=_test_case_cnt)
        except JSONDecodeError:
            print(f"Failed to decode slice_result.jsonl for {_method_to_test}")

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures: List[Future] = list([])
        for method_to_test in meta_info['method_name_to_idx']:
            futures.append(pool.submit(thread_init_generation, method_to_test))
        with tqdm(total=len(futures)) as pbar:
            for future in as_completed(futures):
                pbar.update(1)
                future.result()


if __name__ == "__main__":
    main()
