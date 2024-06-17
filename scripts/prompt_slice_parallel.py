import argparse
import json
from pymongo import MongoClient
from concurrent.futures import Future
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from generator.openlimit import ChatRateLimiter
from tqdm import tqdm

from procedures import get_slices
from utils.config import *
from generator import open_generator

print(f"Please check the working dir {os.getcwd()}. For stability, sys.path will not be modified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_name", required=True)
    args = parser.parse_args()
    project_name = args.project_name

    # setup db
    client = MongoClient(mongo_url, mongo_port)
    db = client[project_name]
    print(f"Mongo url: {mongo_url}:{mongo_port}")
    print(f"Playground dir: {os.path.join(playground_dir, project_name)}")

    # load meta learning
    with open(os.path.join(playground_dir, project_name, "meta.json"), "r") as file:
        meta_info = json.load(file)
    print(f"Counting {len(meta_info['idx_to_method_name'])} methods to test")

    # define thread
    monitor = ChatRateLimiter(request_limit=9000, token_limit=900000, bucket_size_in_seconds=60)

    def thread_slice_generation(_method_to_test):
        _slicer = get_slices.SliceInfoGenerator("prompts/no_mock",
                                                "system_gen.jinja2",
                                                "gen_slice.jinja2")
        _chatter = open_generator.OpenGenerator(key=api_keys, request_url=model_url,
                                                model='gpt-3.5-turbo-0125',
                                                monitor=monitor)  # share the monitor. Since multi-thread has GIL lock
        _log_dir = os.path.join(playground_dir, project_name, "methods",
                                meta_info['method_name_to_idx'][_method_to_test])
        os.makedirs(_log_dir, exist_ok=True)
        _slicer.work(_log_dir, db.get_collection(_method_to_test), _chatter)

    # thread execute
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures: List[Future] = list([])
        for method_to_test in meta_info['method_name_to_idx']:
            futures.append(pool.submit(thread_slice_generation, method_to_test))
        with tqdm(total=len(futures)) as pbar:
            for _ in as_completed(futures):
                pbar.update(1)


if __name__ == "__main__":
    main()
