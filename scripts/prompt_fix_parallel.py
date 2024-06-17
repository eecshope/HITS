import argparse
import glob
import json
import shutil
from typing import Dict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from pymongo import MongoClient
from tqdm import tqdm

from generator import open_generator
from generator.openlimit import ChatRateLimiter
from procedures import fix_code
from utils.config import *

print(f"Please check the working dir {os.getcwd()}. For stability, sys.path will not be modified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_name", required=True)
    parser.add_argument("--init_test", action='store_true')
    parser.add_argument("--perform_cleaning", action='store_true')
    parser.add_argument("--fixing", action='store_true')
    parser.add_argument("--wo_slice", action='store_true')
    args = parser.parse_args()
    project_name = args.project_name

    # setup db
    client = MongoClient(mongo_url, mongo_port)
    db = client[project_name]
    print(f"Mongo url: {mongo_url}:{mongo_port}")
    print(f"Playground dir: {os.path.join(playground_dir, project_name)}")
    print(f"fixing? {args.fixing}")
    print(f"wo_slice? {args.wo_slice}")
    mark = input("\nContinue? (y to continue)")
    if mark != 'y':
        return

    if args.wo_slice:
        prompt_root = 'prompts/no_slice'
        method_workspaces_prefix = 'methods_no_slice'
    else:
        prompt_root = 'prompts/no_mock'
        method_workspaces_prefix = 'methods'

    # load meta info
    with open(os.path.join(playground_dir, project_name, "meta.json"), "r") as file:
        meta_info = json.load(file)
    print(f"Counting {len(meta_info['idx_to_method_name'])} methods to test")

    if args.init_test:
        print(f"Init testing...")
        # Concurrent test all methods-to-test
        failed_tests = dict({})

        if args.perform_cleaning:
            steps_dir = glob.glob(f"{playground_dir}/{project_name}/{method_workspaces_prefix}/**/fixing")
            print("Cleaning these dir: \n" + "\n".join(steps_dir))
            for step_dir in steps_dir:
                shutil.rmtree(step_dir)

        def thread_init_test(_method_to_test):
            _code_fixer = fix_code.TestFixer(prompt_root,
                                             "system_repair.jinja2", "repair.jinja2")
            _log_dir = os.path.join(playground_dir, project_name, method_workspaces_prefix,
                                    meta_info['method_name_to_idx'][_method_to_test])
            if args.fixing and not os.path.exists(os.path.join(_log_dir.__str__(), 'slice_fixing')):
                return f"{_method_to_test} has not 'slice_fixing'"
            elif not args.fixing and not os.path.exists(os.path.join(_log_dir.__str__(), 'steps')):
                return f"{_method_to_test} has no 'steps'"
            return _code_fixer.init_test(_log_dir, meta_info['put_path'], db.get_collection(_method_to_test),
                                         fixing=args.fixing)

        with ThreadPoolExecutor(max_workers=8) as pool:
            init_test_records: Dict[str, Future] = {}
            for method_to_test in meta_info['method_name_to_idx']:
                init_test_records[method_to_test] = pool.submit(thread_init_test, method_to_test)
            for key in tqdm(init_test_records):
                failed_tests[key] = init_test_records[key].result()
    else:
        # method_to_test = 'org.apache.commons.csv.CSVParser.nextRecord()'
        # collect all tasks
        tasks = list([])
        fixed_result = dict({})
        for method_to_test in meta_info['method_name_to_idx']:
            # if method_to_test != 'org.apache.commons.csv.CSVParser.nextRecord()':
            #    continue
            log_dir = os.path.join(playground_dir, project_name, method_workspaces_prefix,
                                   meta_info['method_name_to_idx'][method_to_test])
            with open(os.path.join(log_dir.__str__(), 'fixing', 'init_test_failed.txt'), "r") as file:
                failed_test_list = [item for item in file.read().strip().split('\n')
                                    if item != "" and (not args.fixing or 'Fix' in item)]
            for failed_case in failed_test_list:
                tasks.append((method_to_test, log_dir, failed_case))
            fixed_result[method_to_test] = {'to_fix': len(failed_test_list), "fixed": 0}

        monitor = ChatRateLimiter(9000, 900000, 60)

        def slice_concurrent_fix(_method_to_test, _log_dir, _failed_case):
            if not args.fixing:
                _code_fixer = fix_code.TestFixer(prompt_root, "system_repair.jinja2", "repair.jinja2")
            else:
                _code_fixer = fix_code.TestFixer(prompt_root, "system_repair.jinja2", "repair_patch.jinja2")
            _chatter = open_generator.OpenGenerator(key=api_keys,
                                                    request_url=model_url,
                                                    model='gpt-3.5-turbo-0125', monitor=monitor)
            try:
                _fix_result = _code_fixer.single_unitest_fix(_log_dir,
                                                             db.get_collection(_method_to_test),
                                                             _failed_case,
                                                             meta_info['put_path'],
                                                             _chatter)
            except RuntimeError as e:
                print(e, "error catch")
                _fix_result = False
            return _method_to_test, _fix_result

        with ThreadPoolExecutor(max_workers=12) as pool:
            works = list([])
            for task in tasks:
                method_to_test, log_dir, failed_case = task
                works.append(pool.submit(slice_concurrent_fix, method_to_test, log_dir, failed_case))
            with tqdm(total=len(works)) as pbar:
                for future in as_completed(works):
                    method_to_test, fix_result = future.result()
                    fixed_result[method_to_test]['fixed'] += fix_result
                    pbar.update(1)

        for method_to_test in fixed_result:
            print(f"For {method_to_test}: {fixed_result[method_to_test]['fixed']}/{fixed_result[method_to_test]['to_fix']}")


if __name__ == "__main__":
    main()
